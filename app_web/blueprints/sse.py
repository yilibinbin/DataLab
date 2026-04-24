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

import logging
from typing import Iterator

from flask import Blueprint, Response, request

from app_web.streaming import SSE_CONTENT_TYPE, sse_stream

__all__ = ["bp", "build_sse_response"]

_logger = logging.getLogger(__name__)

bp = Blueprint("sse", __name__)


# Model-identifier aliases — matches the CLI's alias table. Kept in
# sync manually; a future refactor could centralise these.
_MODEL_ALIASES = {
    "linear": "M1",
    "quadratic": "M2",
    "cubic": "M3",
    "log": "M4",
    "inverse": "M5",
    "exponential": "M7",
}


def _parse_float_csv(raw: str | None, field_name: str) -> list[float]:
    """Parse ``"1.0,2.0,3.0"`` → ``[1.0, 2.0, 3.0]``. Raises
    ValueError with a field-named message on any non-numeric cell."""
    if not raw:
        raise ValueError(f"missing required field {field_name!r}")
    cells = [c.strip() for c in raw.split(",") if c.strip()]
    if not cells:
        raise ValueError(f"field {field_name!r} is empty")
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
    Caller checks existence in AUTO_MODELS."""
    normalized = (raw or "").strip()
    return _MODEL_ALIASES.get(normalized.lower(), normalized)


def _single_fit_events(
    xs: list[float],
    ys: list[float],
    model_id: str,
    precision: int,
) -> Iterator[tuple[str, dict]]:
    """Yield events for a single-model fit. Protocol:
        started → progress (fitting) → result (success) OR error.
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

    try:
        with precision_guard(precision):
            fit_result = fit_linear_model(
                definition, xs, ys, precision=precision
            )
    except Exception as exc:  # noqa: BLE001
        yield ("error", {
            "error": type(exc).__name__,
            "message": str(exc)[:500],
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
    """
    from fitting.auto_models import AUTO_MODELS, fit_linear_model
    from shared.precision import precision_guard

    yield ("started", {
        "n_points": len(xs), "precision": precision,
        "n_models": len(AUTO_MODELS),
    })

    candidates: list[dict] = []
    with precision_guard(precision):
        for index, definition in enumerate(AUTO_MODELS, start=1):
            try:
                fit_result = fit_linear_model(
                    definition, xs, ys, precision=precision
                )
                aic = float(fit_result.aic) if fit_result.aic is not None else None
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
                payload = {
                    "model": definition.identifier,
                    "label": definition.label,
                    "status": "failed",
                    "index": index,
                    "total": len(AUTO_MODELS),
                    "error": str(exc)[:200],
                }
            yield ("progress", payload)

    # Rank by AIC ascending; None AIC go to the back.
    ranked = sorted(
        candidates,
        key=lambda c: (c["aic"] is None, c["aic"] if c["aic"] is not None else 0.0),
    )
    yield ("result", {
        "best": ranked[0] if ranked else None,
        "candidates": ranked[:5],
        "n_successful": len(candidates),
    })


def build_sse_response(events: Iterator[tuple[str, dict]]) -> Response:
    """Wrap a (name, payload) generator into a Flask SSE Response.

    Sets the standard anti-buffering headers so nginx / Cloudflare
    don't accumulate the stream into a single chunk. Factored out so
    tests can call it directly with a handwritten generator.
    """
    response = Response(sse_stream(events), mimetype=SSE_CONTENT_TYPE)
    # These three are the canonical combination for SSE through proxies.
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


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
    """Single-model fit with progress events."""
    xs, ys, model_id, precision, err = _extract_and_validate_common(
        require_model=True
    )

    def _gen() -> Iterator[tuple[str, dict]]:
        if err is not None:
            yield ("error", {"error": "BadRequest", "message": err})
            return
        yield from _single_fit_events(xs, ys, model_id, precision)

    return build_sse_response(_gen())


@bp.route("/api/auto-fit/stream", methods=["GET"])
def auto_fit_stream():
    """Auto-fit with per-model progress events."""
    xs, ys, _model, precision, err = _extract_and_validate_common(
        require_model=False
    )

    def _gen() -> Iterator[tuple[str, dict]]:
        if err is not None:
            yield ("error", {"error": "BadRequest", "message": err})
            return
        yield from _auto_fit_events(xs, ys, precision)

    return build_sse_response(_gen())
