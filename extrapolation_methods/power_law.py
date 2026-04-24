"""High-precision power-law extrapolation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.precision import precision_guard


class PowerLawComputationError(RuntimeError):
    """Raised when the power-law extrapolation cannot converge."""


@dataclass
class PowerLawConfig:
    """Configuration for the scientific power-law extrapolation."""

    x_values: Sequence[float | int | str | mp.mpf]
    precision: int = 50
    exponent_override: float | int | str | mp.mpf | None = None
    initial_guess: float | int | str | mp.mpf = 1.0
    seed_guesses: Sequence[float | int | str | mp.mpf] | None = None

    def normalized_x(self) -> tuple[mp.mpf, mp.mpf, mp.mpf]:
        if len(self.x_values) != 3:
            raise PowerLawComputationError(
                _dual_msg(
                    "Power-law extrapolation 需要恰好三个基数 (x1, x2, x3)。",
                    "Power-law extrapolation requires exactly three bases (x1, x2, x3).",
                )
            )
        return tuple(_mpf_from_numeric(value, "x") for value in self.x_values)  # type: ignore[return-value]

    def normalized_precision(self) -> int:
        return max(int(self.precision or 0), 1)

    def normalized_initial_guess(self) -> mp.mpf:
        return _mpf_from_numeric(self.initial_guess, "p0")

    def normalized_override(self) -> mp.mpf | None:
        if self.exponent_override in ("", None):
            return None
        return _mpf_from_numeric(self.exponent_override, "p")


@dataclass
class PowerLawResult:
    """Result of a power-law extrapolation."""

    value: mp.mpf
    exponent: mp.mpf
    amplitude: mp.mpf


def extrapolate_power_law(
    config: PowerLawConfig,
    energies: Sequence[float | int | str | mp.mpf],
) -> PowerLawResult:
    """Apply the research-grade power-law extrapolation."""

    if len(energies) != 3:
        raise PowerLawComputationError(
            _dual_msg(
                "需要三列能量数据 (E1, E2, E3)。",
                "Expected three energy columns (E1, E2, E3).",
            )
        )

    with precision_guard(config.normalized_precision()):
        x1, x2, x3 = config.normalized_x()
        e_values = [_mpf_from_numeric(val, f"E{i+1}") for i, val in enumerate(energies)]
        E1, E2, E3 = e_values
        # Derive degeneracy eps from mp.eps (the unit roundoff at the current
        # precision) with a modest safety factor, so the threshold tracks the
        # user's requested dps rather than being clamped halfway down.
        eps = mp.eps * mp.mpf(10) ** 2

        def _too_close(a: mp.mpf, b: mp.mpf) -> bool:
            scale = max(mp.fabs(a), mp.fabs(b), mp.mpf("1"))
            return mp.fabs(a - b) <= eps * scale

        if _too_close(E2, E3):
            raise PowerLawComputationError(
                _dual_msg(
                    "E2 与 E3 太接近，无法计算 R=(E1-E2)/(E2-E3)。",
                    "E2 and E3 are too close to compute R=(E1-E2)/(E2-E3).",
                )
            )

        R = (E1 - E2) / (E2 - E3)
        exponent_override = config.normalized_override()

        if exponent_override is not None:
            p_sol = exponent_override
        else:
            def residual(p: mp.mpf) -> mp.mpf:
                numerator = mp.power(x1, -p) - mp.power(x2, -p)
                denominator = mp.power(x2, -p) - mp.power(x3, -p)
                if _too_close(denominator, mp.mpf("0")):
                    raise PowerLawComputationError(
                        _dual_msg(
                            "x2^{-p} 与 x3^{-p} 太接近，无法求解 p。",
                            "x2^{-p} and x3^{-p} are too close; cannot solve p.",
                        )
                    )
                return numerator / denominator - R

            def _solve_exponent() -> mp.mpf:
                """Try multiple seeds to reduce sensitivity to local roots."""
                seeds_raw: list[mp.mpf] = []
                if config.seed_guesses:
                    for idx, raw in enumerate(config.seed_guesses, 1):
                        seeds_raw.append(_mpf_from_numeric(raw, f"p_seed[{idx}]"))
                p0 = config.normalized_initial_guess()
                seeds_raw.extend(
                    [
                        p0,
                        mp.mpf("0.5") * p0,
                        mp.mpf("2.0") * p0,
                        mp.mpf("1.0"),
                        mp.mpf("-1.0"),
                    ]
                )
                seeds = []
                seen = set()
                for seed in seeds_raw:
                    key = mp.nstr(seed, 30)
                    if key not in seen:
                        seeds.append(seed)
                        seen.add(key)
                # Scale findroot tolerance with the active precision so
                # high-dps runs are not silently capped at mpmath's default
                # maxsteps=10 / tol=1e-15 (mirrors R10 C4 fix in hp_fitter).
                tol = mp.mpf(10) ** (-(mp.dps - 5))
                maxsteps = max(50, mp.dps)
                best_p: mp.mpf | None = None
                best_resid: mp.mpf | None = None
                last_error: Exception | None = None
                for seed in seeds:
                    try:
                        candidate = mp.findroot(
                            residual, seed, tol=tol, maxsteps=maxsteps
                        )
                        r_val = mp.fabs(residual(candidate))
                        if best_resid is None or r_val < best_resid:
                            best_resid = r_val
                            best_p = candidate
                    except PowerLawComputationError:
                        raise
                    except Exception as exc:  # pragma: no cover - mpmath internal
                        last_error = exc
                        continue
                if best_p is None:
                    detail = f"{last_error}" if last_error else "no seed succeeded"
                    raise PowerLawComputationError(
                        _dual_msg(
                            f"求解幂律指数 p 失败: {detail}",
                            f"Failed to solve power-law exponent p: {detail}",
                        )
                    )
                return best_p

            try:
                p_sol = _solve_exponent()
            except PowerLawComputationError:
                raise
            except Exception as exc:  # pragma: no cover - relies on mpmath internals
                raise PowerLawComputationError(
                    _dual_msg(
                        f"求解幂律指数 p 失败: {exc}",
                        f"Failed to solve power-law exponent p: {exc}",
                    )
                ) from exc

        if mp.isnan(p_sol) or mp.isinf(p_sol):
            raise PowerLawComputationError(
                _dual_msg(
                    "求解到的幂律指数无效（NaN/Inf）。",
                    "Solved power-law exponent is invalid (NaN/Inf).",
                )
            )
        if mp.fabs(p_sol) > mp.mpf("1e6"):
            raise PowerLawComputationError(
                _dual_msg(
                    f"求解到的幂律指数绝对值过大: {p_sol}",
                    f"Solved power-law exponent magnitude is too large: {p_sol}",
                )
            )

        numerator = E1 - E2
        denominator = mp.power(x1, -p_sol) - mp.power(x2, -p_sol)
        if _too_close(denominator, mp.mpf("0")):
            raise PowerLawComputationError(
                _dual_msg(
                    "幂律拟合中出现除零，x1^{-p} 与 x2^{-p} 太接近。",
                    "Division by zero in power-law fit: x1^{-p} and x2^{-p} are too close.",
                )
            )

        amplitude = numerator / denominator
        extrapolated = E1 - amplitude * mp.power(x1, -p_sol)

        return PowerLawResult(
            value=extrapolated,
            exponent=p_sol,
            amplitude=amplitude,
        )


def _mpf_from_numeric(value: float | int | str | mp.mpf, label: str) -> mp.mpf:
    try:
        return mp.mpf(value)
    except (ValueError, TypeError):
        raise PowerLawComputationError(
            _dual_msg(
                f"{label} 无法解析为数字: {value!r}",
                f"{label} could not be parsed as a number: {value!r}",
            )
        )
