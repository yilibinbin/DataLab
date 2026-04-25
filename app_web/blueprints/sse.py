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
- x/y are kept as strings in the request layer and only materialised
  to ``mp.mpf`` INSIDE the locked ``precision_guard`` region — this
  avoids an early ``float()`` cast destroying high-precision decimal
  input (e.g., a value with 60 significant digits would otherwise
  round to a double).
- Result payload capped via the SSE helper's MAX_SSE_FRAME_BYTES,
  which is enforced inside ``format_sse_event``.
- All mpmath work serialises through the SHARED app-wide
  ``mpmath_lock`` exposed by ``app_web._security_shim`` — the same
  lock used by every other ``@mpmath_synchronized`` view, so an
  SSE fit cannot race with a regular ``/fit`` POST on ``mp.dps``.
"""

from __future__ import annotations

import collections
import functools
import logging
import math
import os
import threading
import time
from typing import Iterator

import mpmath as mp
from flask import Blueprint, Response, request

from app_web._security_shim import mpmath_lock
from app_web.streaming import SSE_CONTENT_TYPE, sse_stream

__all__ = ["bp", "build_sse_response"]

_logger = logging.getLogger(__name__)

bp = Blueprint("sse", __name__)

# Shared serialisation lock — re-exported from ``app_web._security_shim``.
# mpmath's ``mp.dps`` is process-global; concurrent SSE requests
# inside a threaded WSGI worker (Flask dev server, waitress,
# gunicorn's gthread worker) would race on it. Using the SAME lock
# as ``mpmath_synchronized`` (the decorator wrapping every other
# precision-changing view) guarantees an SSE fit cannot interleave
# with a regular POST /fit on ``mp.dps``. Throughput cost: at most
# one mpmath compute at a time per worker process. Real deployments
# scale by adding worker processes, not threads.
_MP_SERIAL_LOCK = mpmath_lock

# DoS defence — per-point cost
# ---------------------------------------------------------------
# Upper bound on array length accepted from the query string. A
# pathological caller could otherwise pass x=<10_000_000 cells> and
# pin a Flask worker indefinitely. 5 000 points is well above typical
# scientific workloads (most papers use < 100) and caps the fit
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
#
# A long-running server behind a wide NAT could accumulate thousands
# of empty deques (one per source IP that fired a single request then
# never returned). Every Nth admission we opportunistically evict IPs
# whose deques are empty and whose last entry is older than one
# RATE_WINDOW_SECONDS window. ``_RATE_GC_EVERY`` controls how often
# — trading scan cost against max accumulation.
_RATE_HISTORY: dict[str, collections.deque] = {}
_RATE_LOCK = threading.Lock()
_RATE_ADMISSIONS_SINCE_GC = 0
_RATE_GC_EVERY = 256
RATE_MAX_REQUESTS = 10
RATE_WINDOW_SECONDS = 60.0

@functools.lru_cache(maxsize=1)
def _warn_rate_bypass_once() -> None:
    """Log a single WARNING the first time the rate-limit bypass env
    var is observed. ``lru_cache(maxsize=1)`` is naturally thread-
    safe (CPython holds an internal lock around cache lookups), and
    tests reset via ``_warn_rate_bypass_once.cache_clear()`` rather
    than touching a separate module-level flag."""
    _logger.warning(
        "DATALAB_SSE_DISABLE_RATE_LIMIT is set — SSE rate limiter is "
        "OFF for this process. Production deployments MUST NOT set "
        "this variable."
    )


def _rate_gc_locked(now: float) -> None:
    """Evict empty / fully-expired deques from ``_RATE_HISTORY``.

    Must be called with ``_RATE_LOCK`` held. O(N) scan but N is the
    number of unique recent IPs, not the total requests seen — far
    smaller.
    """
    cutoff = now - RATE_WINDOW_SECONDS
    dead: list[str] = []
    for ip, hist in _RATE_HISTORY.items():
        # Drain expired timestamps; if the deque ends up empty the
        # IP hasn't been seen in a full window and we can forget it.
        # ``< cutoff`` is the standard half-open sliding-window
        # convention; exact equality on monotonic floats is
        # impossible in practice so the choice doesn't affect
        # real traffic.
        while hist and hist[0] < cutoff:
            hist.popleft()
        if not hist:
            dead.append(ip)
    for ip in dead:
        _RATE_HISTORY.pop(ip, None)


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the client is within the per-IP rate budget.

    Evicts expired entries before checking, so a client that was
    previously throttled but has since cooled down unblocks itself.

    The limiter is a no-op when ``app.config["TESTING"]`` is True or
    the ``DATALAB_SSE_DISABLE_RATE_LIMIT`` env var is set — both are
    production-never-true flags used by the test suite to exercise
    the full SSE surface without being artificially rate-limited
    between tests. Real deployments leave both unset; if the env
    var IS set in a deployment, we log a WARNING once at process
    start so the misconfig is visible.
    """
    # Hoist the global to the top of the function so the
    # `+= 1` / `= 0` writes below are unambiguous regardless of
    # which conditional branch ran first. Previously the global
    # statement lived inside a conditional, making the intent
    # easy to break in a future refactor.
    global _RATE_ADMISSIONS_SINCE_GC

    try:
        from flask import current_app

        if current_app.config.get("TESTING"):
            return True
    except Exception:  # noqa: BLE001 - may run outside an app context
        pass

    if os.environ.get("DATALAB_SSE_DISABLE_RATE_LIMIT"):
        _warn_rate_bypass_once()
        return True

    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SECONDS
    with _RATE_LOCK:
        hist = _RATE_HISTORY.setdefault(client_ip, collections.deque())
        # ``< cutoff`` matches _rate_gc_locked above (standard
        # half-open sliding window).
        while hist and hist[0] < cutoff:
            hist.popleft()
        if len(hist) >= RATE_MAX_REQUESTS:
            return False
        hist.append(now)
        _RATE_ADMISSIONS_SINCE_GC += 1
        if _RATE_ADMISSIONS_SINCE_GC >= _RATE_GC_EVERY:
            _rate_gc_locked(now)
            _RATE_ADMISSIONS_SINCE_GC = 0
        return True


def _client_ip() -> str:
    """Resolve the rate-limit key for the current request.

    Simply returns ``request.remote_addr`` — the safe default. When
    the deployment is behind a reverse proxy, the operator sets
    ``DATALAB_TRUST_PROXY_HEADERS=1`` and ``create_app`` wraps the
    WSGI app with ``werkzeug.middleware.proxy_fix.ProxyFix``, which
    rewrites ``remote_addr`` from ``X-Forwarded-For``. No manual
    header parsing is needed here — ProxyFix is the canonical fix
    and correctly refuses to trust XFF from non-proxy hops.

    A deployment that exposes Flask directly to the internet MUST
    NOT set the env var; in that case ``remote_addr`` is the
    connecting socket's IP (which the client cannot forge without
    IP spoofing, which is a separate problem outside the Flask
    layer).
    """
    return request.remote_addr or "unknown"


def _parse_numeric_csv_strings(
    raw: str | None, field_name: str
) -> list[str]:
    """Parse ``"1.0,2.0,3.0"`` → ``["1.0", "2.0", "3.0"]``.

    Returns the raw STRING cells (validated to look like numbers)
    rather than ``float`` values. The caller is expected to convert
    each cell to ``mp.mpf`` inside a ``precision_guard`` block, so
    high-precision input (60+ significant digits) is preserved
    instead of being silently rounded to a double.

    Raises ValueError on any non-numeric cell, empty input, or input
    exceeding ``MAX_SSE_INPUT_POINTS``.
    """
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
    # Validate each cell parses as a finite number — but keep the
    # original string for downstream mp.mpf conversion. We use
    # ``float()`` only to detect garbage; the string is what we pass
    # forward.
    for cell in cells:
        try:
            value = float(cell)
        except ValueError as exc:
            raise ValueError(
                f"field {field_name!r} contains non-numeric value: {cell!r}"
            ) from exc
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"field {field_name!r} contains non-finite value: {cell!r}"
            )
    return cells


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


# Exception types we treat as expected per-model failures during
# auto-fit (and thus emit a "model failed" progress event for, while
# continuing to the next model). Any other exception is a programmer
# bug or systemic failure — those propagate out so the SSE generator
# can convert them to a single 'error' event and close, rather than
# silently masking them as "every model failed individually".
_AUTO_FIT_EXPECTED_FAILURES: tuple[type[BaseException], ...] = (
    ValueError,        # bad input shape, sign, monotonicity
    ArithmeticError,   # mpmath divide-by-zero, OverflowError, etc.
    RuntimeError,      # LM solver convergence failure
    NotImplementedError,  # model rejecting an unsupported config
)


def _materialise_mpf_pairs(
    xs_str: list[str], ys_str: list[str], precision: int
) -> tuple[list, list]:
    """Convert string CSV cells to ``mp.mpf`` lists at the given
    precision. Must be called with ``precision_guard(precision)``
    already entered so ``mp.dps`` is set correctly during conversion.

    Strings are passed unchanged to ``mp.mpf`` so a 60-digit input
    keeps its precision (whereas the previous early-``float`` path
    would round to ~17 digits before reaching the fitter).
    """
    xs = [mp.mpf(s) for s in xs_str]
    ys = [mp.mpf(s) for s in ys_str]
    return xs, ys


def _single_fit_events(
    xs_str: list[str],
    ys_str: list[str],
    model_id: str,
    precision: int,
) -> Iterator[tuple[str, dict]]:
    """Yield events for a single-model fit. Protocol:
        started → progress (fitting) → result (success) OR error.

    Serialises mpmath work via ``_MP_SERIAL_LOCK`` (the shared
    app-wide lock) so concurrent SSE requests don't race on
    ``mp.dps`` (which is process-global in mpmath). Enforces
    ``MAX_SSE_WALLCLOCK_SECONDS`` so a slow fit (or slow client)
    can't pin a worker indefinitely.

    ``xs_str`` / ``ys_str`` are STRING cells; conversion to
    ``mp.mpf`` happens inside the locked ``precision_guard`` region
    so high-precision input survives unrounded.
    """
    from fitting.auto_models import AUTO_MODELS, fit_linear_model
    from shared.precision import precision_guard

    yield ("started", {
        "n_points": len(xs_str), "model": model_id, "precision": precision,
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
            xs, ys = _materialise_mpf_pairs(xs_str, ys_str, precision)
            fit_result = fit_linear_model(
                definition, xs, ys, precision=precision
            )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "fit_stream failed: model=%s n_points=%d precision=%d: %s",
            model_id, len(xs_str), precision, exc, exc_info=True,
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
    xs_str: list[str],
    ys_str: list[str],
    precision: int,
) -> Iterator[tuple[str, dict]]:
    """Yield events for auto-fit across every registered linear model.

    Protocol::

        started → progress (per model) → result (ranked list) OR error

    The implementation drives the per-model loop INSIDE this generator
    so each model's completion triggers an immediate ``yield``. The
    existing ``auto_fit_dataset`` builds everything in a list, which
    defeats streaming — we replicate the loop here for this endpoint.

    Lock discipline: ``_MP_SERIAL_LOCK`` is acquired ONLY around the
    actual ``fit_linear_model`` call — not around the ``yield``. The
    previous design held the lock across yields, which serialised
    slow SSE clients with compute work and let one buffering proxy
    pin the lock for minutes. With per-model acquisition, concurrent
    SSE requests interleave at model boundaries and the lock is
    never held during network I/O.

    GUARD: no mpmath calls may appear between the ``with`` block exit
    and the ``yield ("progress", ...)``. The ``float()`` and
    ``math.isnan`` casts on ``aic`` operate on Python floats, not
    mpmath, so the inter-iteration window is safe.

    Honours ``MAX_SSE_WALLCLOCK_SECONDS`` — if the total fit time
    exceeds the budget, emits a ``timeout`` error event between
    iterations and closes. Per-model exception text is sanitised
    to the class name only to avoid leaking mpmath internals.

    Per-model exception handling: ONLY the expected numerical /
    domain failures listed in ``_AUTO_FIT_EXPECTED_FAILURES`` are
    treated as "this model didn't converge, try the next". Other
    exceptions (programmer bugs, KeyboardInterrupt, MemoryError,
    serialisation errors) propagate out and are converted to a
    single terminal 'error' event by the SSE generator wrapper —
    surfacing what would otherwise be silently swallowed as
    "AllModelsFailed".
    """
    from fitting.auto_models import AUTO_MODELS, fit_linear_model
    from shared.precision import precision_guard

    yield ("started", {
        "n_points": len(xs_str), "precision": precision,
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

    # Materialise xs / ys ONCE before the per-model loop. The strings
    # don't change between iterations and the conversion is O(N×digits);
    # repeating it for every model wastes work proportional to
    # len(AUTO_MODELS) × len(xs_str). The lock + precision_guard pair
    # ensures the conversion happens at the correct mp.dps without
    # racing other SSE requests.
    try:
        with _MP_SERIAL_LOCK, precision_guard(precision):
            xs, ys = _materialise_mpf_pairs(xs_str, ys_str, precision)
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "auto_fit_stream: input materialisation failed: %s", exc,
            exc_info=True,
        )
        yield ("error", {
            "error": type(exc).__name__,
            "message": _sanitise_error_message(exc),
        })
        return

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

        # Lock acquired per-model, released BEFORE the yield. mp.dps
        # state leakage across iterations is fine because each fit
        # re-enters precision_guard — the lock just prevents a
        # concurrent SSE request from racing on mp.dps DURING a
        # single fit_linear_model call.
        try:
            with _MP_SERIAL_LOCK, precision_guard(precision):
                fit_result = fit_linear_model(
                    definition, xs, ys, precision=precision
                )
            aic = (
                float(fit_result.aic) if fit_result.aic is not None else None
            )
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
        except _AUTO_FIT_EXPECTED_FAILURES as exc:
            # Numerical / domain failure for this model — log and
            # continue. The protocol contract says the user gets a
            # ranked list of models that DID succeed, and a per-model
            # 'failed' progress event for each that didn't.
            _logger.warning(
                "auto_fit_stream: model %s failed (%s): %s",
                definition.identifier, type(exc).__name__, exc,
            )
            payload = {
                "model": definition.identifier,
                "label": definition.label,
                "status": "failed",
                "index": index,
                "total": len(AUTO_MODELS),
                "error": type(exc).__name__,
            }
        # Yield is OUTSIDE the lock so a slow client receiving the
        # progress frame cannot pin the mp.dps serialiser.
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
    list[str] | None, list[str] | None, str | None, int, str | None
]:
    """Pull xs / ys / model / precision from the request query string.

    Must be called INSIDE the request context (i.e. within the view
    function, not the generator), because Flask tears the context
    down once the view returns — even though the Response is still
    streaming.

    ``xs`` / ``ys`` are returned as STRING lists (the deferred-mpf
    pattern); the generator converts to ``mp.mpf`` inside the
    locked ``precision_guard`` region so high-precision decimal
    input is preserved.

    Returns ``(xs_str, ys_str, model_id, precision, error_message)``.
    If the error message is non-empty, the view should yield an
    ``error`` SSE event and return without doing any computation.
    """
    try:
        xs_str = _parse_numeric_csv_strings(request.args.get("x"), "x")
        ys_str = _parse_numeric_csv_strings(request.args.get("y"), "y")
        if len(xs_str) != len(ys_str):
            raise ValueError(
                f"x and y must have the same length "
                f"(got {len(xs_str)} and {len(ys_str)})"
            )
        precision = _parse_precision(request.args.get("precision"))
        model_id: str | None = None
        if require_model:
            model_id = _resolve_model_id(request.args.get("model", ""))
            if not model_id:
                raise ValueError("missing required field 'model'")
    except ValueError as exc:
        return None, None, None, 50, str(exc)
    return xs_str, ys_str, model_id, precision, None


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

    xs_str, ys_str, model_id, precision, err = _extract_and_validate_common(
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
            yield from _single_fit_events(xs_str, ys_str, model_id, precision)

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

    xs_str, ys_str, _model, precision, err = _extract_and_validate_common(
        require_model=False
    )

    if err is not None:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield ("error", {"error": "BadRequest", "message": err})
    else:
        def _gen() -> Iterator[tuple[str, dict]]:
            yield from _auto_fit_events(xs_str, ys_str, precision)

    return build_sse_response(_gen())
