from __future__ import annotations

from .extrapolation import run_extrapolation
from .fitting import run_fitting
from .jobs import JobMode
from .root_solving import run_root_solving
from .session import CancellationChecker, JobHandler, SessionCallbacks, SessionService
from .statistics import run_statistics
from .uncertainty import run_uncertainty


MIGRATED_CORE_MODES: tuple[JobMode, ...] = (
    JobMode.STATISTICS,
    JobMode.UNCERTAINTY,
    JobMode.EXTRAPOLATION,
    JobMode.FITTING,
    JobMode.ROOT_SOLVING,
)
_CORE_HANDLER_REGISTRY: dict[JobMode, JobHandler] = {
    JobMode.STATISTICS: run_statistics,
    JobMode.UNCERTAINTY: run_uncertainty,
    JobMode.EXTRAPOLATION: run_extrapolation,
    JobMode.FITTING: run_fitting,
    JobMode.ROOT_SOLVING: run_root_solving,
}


def default_core_handlers() -> dict[JobMode | str, JobHandler]:
    """Return the currently migrated core job handlers."""

    return {mode: _CORE_HANDLER_REGISTRY[mode] for mode in MIGRATED_CORE_MODES}


def create_core_session_service(
    callbacks: SessionCallbacks | None = None,
    cancellation_checker: CancellationChecker | None = None,
) -> SessionService:
    """Create a core session service with the default migrated handlers."""

    return SessionService(
        handlers=default_core_handlers(),
        callbacks=callbacks or SessionCallbacks(),
        cancellation_checker=cancellation_checker,
    )


__all__ = ["MIGRATED_CORE_MODES", "create_core_session_service", "default_core_handlers"]
