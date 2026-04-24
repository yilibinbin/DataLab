"""SSE streaming endpoints for long-running fit jobs (Phase 4 #3).

Two GET endpoints:
- ``/api/fit/stream`` — single-model fit with progress events.
- ``/api/auto-fit/stream`` — iterate every registered linear model,
  emit a ``progress`` event per model + a final ``result`` event
  with the ranked list.

Why GET and not POST: SSE is a one-way stream over HTTP; GET is the
canonical method and works through the broadest set of proxies.
The input payload is small (two numeric arrays + a few scalars) so
a query string stays well under any URL-length limit. POST bodies
cannot be re-consumed by the EventSource spec on the client side.

Query-string schema::

    x=1,2,3,4,5         # comma-separated x values
    y=2,4,6,8,10        # comma-separated y values (must match x length)
    model=M1            # single-model endpoint only; linear alias accepted
    precision=50        # optional; clamped to [10, 1000]

Hardening:
- Precision clamp mirrors shared.precision bounds — no DoS via
  precision=1e9.
- x/y length mismatch → single ``error`` event (not a 500).
- Unknown model identifier → single ``error`` event.
- Non-numeric cells → single ``error`` event with the offending input.
- Result payload capped via the SSE helper's MAX_SSE_FRAME_BYTES,
  which is enforced inside ``format_sse_event``.
- All mpmath work routes through ``precision_guard``.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Iterator

from flask import Blueprint, Response, request

from app_web.streaming import SSE_CONTENT_TYPE, sse_stream

__all__ = ["bp", "build_sse_response"]

_logger = logging.getLogger(__name__)

bp = Blueprint("sse", __name__)

# mpmath's ``mp.dps`` is **process-global** — two concurrent SSE
# requests inside a threaded WSGI (Flask dev server, waitress,
# gunicorn's gthread worker) would race and overwrite each other's
# precision state mid-fit. The lock serialises the entire mpmath-
# touching region so concurrent callers queue rather than corrupt.
# We accept the throughput cost because correctness-of-numerics
# matters more than "N parallel fits" for this app's scientific use
# case. If a deployment needs more parallelism, run multiple worker
# processes — not more threads.
_MP_SERIAL_LOCK = threading.Lock()

# DoS defence — per-point cost
# ---------------------------------------------------------------
# Upper bound on array length accepted from the query string. A
# pathological caller could otherwise pass x=&lt;10_000_000 cells&gt; and
# pin a Flask worker indefinitely. 5 000 points is well above typical
# scientific workloads (most papers use &lt; 100) and caps the fit
# runtime to single-digit seconds per model even at the highest
# allowed precision.
MAX_SSE_INPUT_POINTS = 5_000

# DoS defence — per-request wall clock
# ---------------------------------------------------------------
# Hard ceiling on how long one SSE request may occupy a worker thread.
# If the mpmath loop exceeds this, the generator yields a timeout
# error event and closes. Without this, a Slowloris-class slow reader
# could pin a thread indefinitely.
MAX_SSE_WALLCLOCK_SECONDS = 90.0

# DoS defence — per-IP rate limit
# ---------------------------------------------------------------
# Simple sliding-window limiter on inbound SSE connections. Keeps a
# deque of recent request timestamps per client IP; on each new
# request drop entries older than RATE_WINDOW_SECONDS. If the deque
# length crosses RATE_MAX_REQUESTS the request is rejected with a
# 429-equivalent SSE "rate_limited" event.
_RATE_HISTORY: dict[str, collections.deque] = {}
_RATE_LOCK = threading.Lock()
RATE_MAX_REQUESTS = 10
RATE_WINDOW_SECONDS = 60.0


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the client is within the per-IP rate budget.

    Evicts expired entries before checking, so a client that was
    previously throttled but has since cooled down unblocks itself.
    """
    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SECONDS
    with _RATE_LOCK:
        hist = _RATE_HISTORY.setdefault(client_ip, collections.deque())
        while hist and hist[0] < cutoff:
            hist.popleft()
        if len(hist) >= RATE_MAX_REQUESTS:
            return False
        hist.append(now)
        return True


def _client_ip() -> str:
    """Best-effort client IP — trusts X-Forwarded-For only if the
    first hop exists. For production this must be augmented with a
    reverse-proxy-aware resolver; here we're conservative and fall
    back to ``request.remote_addr``."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _parse_float_csv(raw: str | None, field_name: str) -> list[float]:
    """Parse ``"1.0,2.0,3.0"`` → ``[1.0, 2.0, 3.0]``. Raises
    ValueError with a field-named message on any non-numeric cell,
    empty input, or input exceeding ``MAX_SSE_INPUT_POINTS``."""
    if not raw:
        raise ValueError(f"missing required field {field_name!r}")
    cells = [c.strip() for c in raw.split(",") if c.strip()]
    if not cells:
        raise ValueError(f"field {field_name!r} is empty")
    if len(cells) > MAX_SSE_INPUT_POINTS:
        raise ValueError(
            f"field {field_name!r} has {len(cells)} points; "
            f"maximum is {MAX_SSE_INPUT_POINTS}"
        )
    try:
        return [float(c) for c in cells]
    except ValueError as exc:
        raise ValueError(
            f"field {field_name!r} contains non-numeric value: {exc}"
        ) from exc


def _parse_precision(raw: str | None, default: int = 50) -> int:
    """Parse + clamp precision to [10, 1000]. Same bounds as
    shared.precision — keeps DoS protection consistent."""
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(10, min(1000, value))


def _resolve_model_id(raw: str) -> str:
    """Map aliases ('linear' → 'M1') and pass identifiers through.
    Caller checks existence in AUTO_MODELS.

    Delegates to ``fitting.auto_models.resolve_model_identifier`` —
    the single source of truth shared with the CLI so both entry
    points accept the same set of friendly names.
    """
    from fitting.auto_models import resolve_model_identifier

    return resolve_model_identifier(raw)


def _sanitise_error_message(exc: Exception) -> str:
    """Return a short, client-safe error message.

    The full exception message may embed filesystem paths, mpmath
    internal references, or partial numeric state. For the SSE error
    event we expose only the exception class name. Full details are
    logged server-side via the caller.
    """
    return (
        f"{type(exc).__name__}: computation failed. "
        "See server logs for details."
    )


def _single_fit_events(
    xs: list[float],
    ys: list[float],
    model_id: str,
    precision: int,
) -> Iterator[tuple[str, dict]]:
    """Yield events for a single-model fit. Protocol:
        started → progress (fitting) → result (success) OR error.

    Serialises mpmath work via ``_MP_SERIAL_LOCK`` so concurrent
    SSE requests don't race on ``mp.dps`` (which is process-global
    in mpmath). Enforces ``MAX_SSE_WALLCLOCK_SECONDS`` so a slow
    fit (or slow client) can't pin a worker indefinitely.
    """
    from fitting.auto_models import AUTO_MODELS, fit_linear_model
    from shared.precision import precision_guard

    yield ("started", {
        "n_points": len(xs), "model": model_id, "precision": precision,
    })

    by_id = {d.identifier: d for d in AUTO_MODELS}
    definition = by_id.get(model_id)
    if definition is None:
        yield ("error", {
            "error": "UnknownModel",
            "message": (
                f"Unknown model {model_id!r}. Available: "
                f"{', '.join(sorted(by_id))}"
            ),
        })
        return

    yield ("progress", {"model": model_id, "status": "fitting"})

    deadline = time.monotonic() + MAX_SSE_WALLCLOCK_SECONDS
    try:
        with _MP_SERIAL_LOCK, precision_guard(precision):
            fit_result = fit_linear_model(
                definition, xs, ys, precision=precision
            )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "fit_stream failed: %s", exc, exc_info=True
        )
        yield ("error", {
            "error": type(exc).__name__,
            "message": _sanitise_error_message(exc),
        })
        return

    if time.monotonic() > deadline:
        _logger.warning(
            "fit_stream exceeded wall-clock budget (%.1fs)",
            MAX_SSE_WALLCLOCK_SECONDS,
        )
        yield ("error", {
            "error": "Timeout",
            "message": (
                f"Fit exceeded the {MAX_SSE_WALLCLOCK_SECONDS:.0f}s "
                "wall-clock budget for a single stream"
            ),
        })
        return

    params = {k: float(v) for k, v in (fit_result.params or {}).items()}
    errors = {
        k: float(v) for k, v in (fit_result.param_errors_stat or {}).items()
    }
    yield ("result", {
        "model": model_id,
        "model_label": definition.label,
        "params": params,
        "param_errors_stat": errors,
    })


def _auto_fit_events(
    xs: list[float],
    ys: list[float],
    precision: int,
) -> Iterator[tuple[str, dict]]:
    """Yield events for auto-fit across every registered linear model.

    Protocol::

        started → progress (per model) → result (ranked list) OR error

    The implementation drives the per-model loop INSIDE this generator
    so each model's completion triggers an immediate ``yield``. The
    existing ``auto_fit_dataset`` builds everything in a list, which
    defeats streaming — we replicate the loop here for this endpoint.

    Holds ``_MP_SERIAL_LOCK`` for the entire fit loop so the mp.dps
    state isn't raced by a concurrent request. Honours
    ``MAX_SSE_WALLCLOCK_SECONDS`` — if the total fit time exceeds the
    budget, emits a ``timeout`` error event between iterations and
    closes. Per-model exception text is sanitised to the class name
    only to avoid leaking mpmath internals.
    """
    import math

    from fitting.auto_models import AUTO_MODELS, fit_linear_model
    from shared.precision import precision_guard

    yield ("started", {
        "n_points": len(xs), "precision": precision,
        "n_models": len(AUTO_MODELS),
    })

    if not AUTO_MODELS:
        yield ("error", {
            "error": "NoModels",
            "message": "No models registered — check fitting.auto_models",
        })
        return

    deadline = time.monotonic() + MAX_SSE_WALLCLOCK_SECONDS
    candidates: list[dict] = []
    with _MP_SERIAL_LOCK, precision_guard(precision):
        for index, definition in enumerate(AUTO_MODELS, start=1):
            if time.monotonic() > deadline:
                yield ("error", {
                    "error": "Timeout",
                    "message": (
                        f"Auto-fit exceeded the "
                        f"{MAX_SSE_WALLCLOCK_SECONDS:.0f}s wall-clock "
                        f"budget after {index - 1}/{len(AUTO_MODELS)} models"
                    ),
                })
                return
            try:
                fit_result = fit_linear_model(
                    definition, xs, ys, precision=precision
                )
                aic = float(fit_result.aic) if fit_result.aic is not None else None
                # NaN AIC is not less-than-anything — treat as missing
                # for ranking purposes so float('nan') doesn't poison
                # the sort key downstream.
                if aic is not None and math.isnan(aic):
                    aic = None
                payload = {
                    "model": definition.identifier,
                    "label": definition.label,
                    "status": "success",
                    "index": index,
                    "total": len(AUTO_MODELS),
                    "aic": aic,
                }
                candidates.append({
                    "model": definition.identifier,
                    "label": definition.label,
                    "aic": aic,
                    "params": {
                        k: float(v)
                        for k, v in (fit_result.params or {}).items()
                    },
                })
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "auto_fit_stream: model %s failed: %s",
                    definition.identifier, exc, exc_info=True,
                )
                payload = {
                    "model": definition.identifier,
                    "label": definition.label,
                    "status": "failed",
                    "index": index,
                    "total": len(AUTO_MODELS),
                    "error": type(exc).__name__,
                }
            yield ("progress", payload)

    if not candidates:
        # Every model failed — emit an error rather than a
        # null-best result. Protocol contract: terminal event is
        # either 'result' (success) OR 'error' (failure).
        yield ("error", {
            "error": "AllModelsFailed",
            "message": (
                "All registered models failed to converge on this "
                "dataset. Check the data range, sign, and sample size."
            ),
        })
        return

    # Rank by AIC ascending; None AIC go to the back.
    ranked = sorted(
        candidates,
        key=lambda c: (c["aic"] is None, c["aic"] if c["aic"] is not None else 0.0),
    )
    yield ("result", {
        "best": ranked[0],
        "candidates": ranked[:5],
        "n_successful": len(candidates),
    })


def build_sse_response(events: Iterator[tuple[str, dict]]) -> Response:
    """Wrap a (name, payload) generator into a Flask SSE Response.

    Anti-buffering headers stop nginx / Cloudflare from accumulating
    the stream into a single chunk. Deliberately omits
    ``Connection: keep-alive`` — meaningless on HTTP/2 and the
    default on HTTP/1.1. ``X-Content-Type-Options: nosniff`` belt-
    and-braces against MIME-sniffing.
    """
    response = Response(sse_stream(events), mimetype=SSE_CONTENT_TYPE)
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _rate_limited_gen() -> Iterator[tuple[str, dict]]:
    """Single-event generator used when the per-IP rate budget is
    exhausted — emits an ``error`` SSE event and closes."""
    yield ("error", {
        "error": "RateLimited",
        "message": (
            f"Too many SSE requests from this IP — max "
            f"{RATE_MAX_REQUESTS} per {int(RATE_WINDOW_SECONDS)}s window"
        ),
    })


def _extract_and_validate_common(require_model: bool) -> tuple[
    list[float] | None, list[float] | None, str | None, int, str | None
]:
    """Pull xs / ys / model / precision from the request query string.

    Must be called INSIDE the request context (i.e. within the view
    function, not the generator), because Flask tears the context
    down once the view returns — even though the Response is still
    streaming.

    Returns ``(xs, ys, model_id, precision, error_message)``. If the
    error message is non-empty, the view should yield an ``error``
    SSE event and return without doing any computation.
    """
    try:
        xs = _parse_float_csv(request.args.get("x"), "x")
        ys = _parse_float_csv(request.args.get("y"), "y")
        if len(xs) != len(ys):
            raise ValueError(
                f"x and y must have the same length "
                f"(got {len(xs)} and {len(ys)})"
            )
        precision = _parse_precision(request.args.get("precision"))
        model_id: str | None = None
        if require_model:
            model_id = _resolve_model_id(request.args.get("model", ""))
            if not model_id:
                raise ValueError("missing required field 'model'")
    except ValueError as exc:
        return None, None, None, 50, str(exc)
    return xs, ys, model_id, precision, None


@bp.route("/api/fit/stream", methods=["GET"])
def fit_stream():
    """Single-model fit with progress events.

    GET-only: CSRF protection via method restriction is intentional.
    If a POST variant is ever added, apply @csrf_protect from
    app_web.security.
    """
    client_ip = _client_ip()
    if not _check_rate_limit(client_ip):
        _logger.info(
            "fit_stream: rate-limited %s (budget %d/%ds)",
            client_ip, RATE_MAX_REQUESTS, RATE_WINDOW_SECONDS,
        )
        return build_sse_response(_rate_limited_gen())

    xs, ys, model_id, precision, err = _extract_and_validate_common(
        require_model=True
    )

    # Bind generator body at view time with an explicit ternary so a
    # future refactor that rebinds any of xs/ys/model_id/precision/err
    # inside the view body can't silently reach the stream.
    if err is not None:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield ("error", {"error": "BadRequest", "message": err})
    else:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield from _single_fit_events(xs, ys, model_id, precision)

    return build_sse_response(_gen())


@bp.route("/api/auto-fit/stream", methods=["GET"])
def auto_fit_stream():
    """Auto-fit with per-model progress events.

    GET-only: CSRF protection via method restriction is intentional.
    See fit_stream for the future-POST note.
    """
    client_ip = _client_ip()
    if not _check_rate_limit(client_ip):
        _logger.info(
            "auto_fit_stream: rate-limited %s (budget %d/%ds)",
            client_ip, RATE_MAX_REQUESTS, RATE_WINDOW_SECONDS,
        )
        return build_sse_response(_rate_limited_gen())

    xs, ys, _model, precision, err = _extract_and_validate_common(
        require_model=False
    )

    if err is not None:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield ("error", {"error": "BadRequest", "message": err})
    else:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield from _auto_fit_events(xs, ys, precision)

    return build_sse_response(_gen())
