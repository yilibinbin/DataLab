"""Sequence acceleration helpers built on top of mpmath."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.integer_validation import strict_int
from shared.precision import precision_guard


class SequenceAccelerationError(RuntimeError):
    """Raised when a sequence accelerator fails to converge."""


@dataclass
class SequenceAcceleratorConfig:
    """Configuration for mpmath-based accelerators."""

    precision: int = 80
    levin_variant: str = "u"

    def sanitized_precision(self) -> int:
        return max(strict_int(self.precision, field_name="precision"), 1)


@dataclass
class SequenceAcceleratorResult:
    """Acceleration output with metadata about the computation."""

    value: mp.mpf
    metadata: dict[str, mp.mpf | str]


def apply_sequence_accelerator(
    method: str,
    sequence_values: Sequence[float | int | str | mp.mpf],
    config: SequenceAcceleratorConfig,
) -> SequenceAcceleratorResult:
    """
    Dispatch to one of the supported accelerators.

    Note: mpmath 的 mp.shanks 实现的是 Wynn ε 算法；“shanks” 与
    “wynn_epsilon” 在核心算法上相同，仅元数据标签不同，用于向用户说明选择。
    """

    if len(sequence_values) < 3:
        raise SequenceAccelerationError(
            _dual_msg(
                "至少需要三列数据才能执行该序列加速方法。",
                "At least three columns are required to perform sequence acceleration.",
            )
        )

    with precision_guard(config.sanitized_precision()):
        mp_sequence = [_mpf_from_numeric(val, f"S{i}") for i, val in enumerate(sequence_values, 1)]
        method_key = method.lower()

        if method_key == "richardson":
            # mpmath.richardson returns the first term for N<4; require >=4 to avoid misleading results.
            if len(mp_sequence) < 4:
                raise SequenceAccelerationError(
                    _dual_msg(
                        "Richardson 序列加速至少需要四列数据。",
                        "Richardson sequence acceleration requires at least four columns.",
                    )
                )
            try:
                limit, cancellation = mp.richardson(mp_sequence)
            except Exception as exc:
                raise SequenceAccelerationError(
                    _dual_msg(
                        f"Richardson 外推失败: {exc}",
                        f"Richardson extrapolation failed: {exc}",
                    )
                ) from exc
            metadata = {"cancellation_weight": mp.fabs(cancellation)}
            return SequenceAcceleratorResult(
                value=limit,
                metadata=metadata,
            )

        if method_key == "shanks":
            return _run_shanks(mp_sequence, variant="shanks")

        if method_key == "wynn_epsilon":
            return _run_shanks(mp_sequence, variant="wynn_epsilon")

        if method_key == "levin_u":
            return _run_levin(mp_sequence, config)

        raise SequenceAccelerationError(
            _dual_msg(
                f"未知的序列加速方法: {method}",
                f"Unknown sequence acceleration method: {method}",
            )
        )


def _run_shanks(
    mp_sequence: Sequence[mp.mpf], variant: str
) -> SequenceAcceleratorResult:
    """Run Wynn epsilon/Shanks using mpmath.shanks; variant is label only."""
    try:
        table = mp.shanks(mp_sequence)
    except Exception as exc:
        raise SequenceAccelerationError(
            _dual_msg(
                f"Shanks/Wynn 计算失败: {exc}",
                f"Shanks/Wynn computation failed: {exc}",
            )
        ) from exc
    if not table or not table[-1]:
        raise SequenceAccelerationError(
            _dual_msg(
                "Shanks/Wynn 结果不包含有效的收敛项。",
                "Shanks/Wynn result does not contain a valid convergent term.",
            )
        )
    last_row = table[-1]
    limit = last_row[-1]
    metadata: dict[str, mp.mpf | str] = {
        "epsilon_depth": mp.mpf(len(table)),
        "last_row_length": mp.mpf(len(last_row)),
    }
    # In mpmath's Wynn-epsilon table the ODD columns are auxiliary (non-convergent) entries that
    # diverge to huge junk magnitudes — only the even columns are convergents. So last_row[-1] is
    # the best convergent and last_row[-3] is the previous convergent, while last_row[-2] is junk.
    # Derive both diagnostics from the proper convergent difference |[-1] - [-3]| (audit A6); a
    # 2-element last row (a 3-input sequence) has no previous convergent, so emit neither rather
    # than a garbage value taken from the auxiliary entry (consumers fall back sanely on absence).
    if len(last_row) >= 3:
        convergent_gap = mp.fabs(last_row[-1] - last_row[-3])
        metadata["error_estimate"] = convergent_gap
        metadata["cancellation_indicator"] = convergent_gap
    metadata["wynn_variant"] = variant
    metadata["note"] = "mp.shanks uses Wynn epsilon algorithm"
    return SequenceAcceleratorResult(value=limit, metadata=metadata)


def _run_levin(
    mp_sequence: Sequence[mp.mpf], config: SequenceAcceleratorConfig
) -> SequenceAcceleratorResult:
    def _sanitize_variant(raw: str | None) -> str:
        variant = (raw or "u").strip().lower()
        if variant in {"u", "t", "v"}:
            return variant
        # Keep default behavior predictable; surface the invalid variant clearly.
        raise SequenceAccelerationError(
            _dual_msg(
                f"Levin 变换类型无效: {raw!r}",
                f"Invalid Levin variant: {raw!r}",
            )
        )

    def _collapse_adjacent_equal(values: list[mp.mpf]) -> list[mp.mpf]:
        """Remove consecutive duplicates to avoid levin 'zero weight' failures."""
        collapsed: list[mp.mpf] = []
        for val in values:
            if not collapsed or val != collapsed[-1]:
                collapsed.append(val)
        return collapsed

    variant = _sanitize_variant(getattr(config, "levin_variant", None))

    try:
        accelerator = mp.levin(variant=variant)
        limit, error = accelerator.update_psum(mp_sequence)
        metadata = {
            "levin_variant": variant,
            "error_estimate": mp.fabs(error),
        }
        return SequenceAcceleratorResult(value=limit, metadata=metadata)
    except Exception as exc:
        # Most common real-world failure: repeated columns -> zero weight (s_n - s_{n-1} == 0).
        message = str(exc)
        if "zero weight" in message and mp_sequence:
            collapsed = _collapse_adjacent_equal(list(mp_sequence))
            removed = len(mp_sequence) - len(collapsed)
            if len(collapsed) >= 3:
                try:
                    accelerator = mp.levin(variant=variant)
                    limit, error = accelerator.update_psum(collapsed)
                    metadata = {
                        "levin_variant": variant,
                        "error_estimate": mp.fabs(error),
                        "deduped_terms": str(removed),
                    }
                    return SequenceAcceleratorResult(value=limit, metadata=metadata)
                except Exception:
                    # Fall through to fallback below.
                    pass

            # Not enough distinct terms for Levin: return the best available approximation instead
            # of silently dropping the row (web UI would otherwise show "no results").
            approx = collapsed[-1] if collapsed else mp_sequence[-1]
            if len(collapsed) >= 2:
                err_est = mp.fabs(collapsed[-1] - collapsed[-2])
            else:
                err_est = mp.mpf("0")
            metadata = {
                "levin_variant": variant,
                "error_estimate": err_est,
                "levin_fallback": "last_value",
                "deduped_terms": str(removed),
            }
            return SequenceAcceleratorResult(value=approx, metadata=metadata)

        raise SequenceAccelerationError(
            _dual_msg(
                f"Levin 加速失败: {exc}",
                f"Levin acceleration failed: {exc}",
            )
        ) from exc


def _mpf_from_numeric(
    value: float | int | str | mp.mpf, label: str
) -> mp.mpf:
    try:
        return mp.mpf(value)
    except (ValueError, TypeError):
        raise SequenceAccelerationError(
            _dual_msg(
                f"{label} 无法解析为数字: {value!r}",
                f"{label} could not be parsed as a number: {value!r}",
            )
        )
