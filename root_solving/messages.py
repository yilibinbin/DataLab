from __future__ import annotations


ROOT_MESSAGE_ZH = {
    "SciPy is unavailable; used mpmath fallback.": "SciPy 不可用，已使用 mpmath 回退。",
    "SciPy solve or validation failed; used mpmath fallback.": "SciPy 求解或验证失败，已使用 mpmath 回退。",
    "SciPy validation failed; used mpmath fallback.": "SciPy 验证失败，已使用 mpmath 回退。",
    "missing result": "缺少结果",
    "no roots": "未找到根",
    "Jacobian is ill-conditioned.": "Jacobian 条件数较差。",
    "Linear uncertainty propagation is only supported for real-valued roots.": "线性不确定度传播仅支持实数根。",
    "Linear uncertainty propagation skipped: root Jacobian is singular or non-finite.": "已跳过线性不确定度传播：根的 Jacobian 奇异或非有限。",
    "Linear uncertainty propagation skipped: root Jacobian is ill-conditioned.": "已跳过线性不确定度传播：根的 Jacobian 条件数较差。",
    "Linear uncertainty propagation skipped: input uncertainties must be finite and non-negative.": "已跳过线性不确定度传播：输入不确定度必须有限且非负。",
    "Second-order root uncertainty is currently supported for scalar real roots only; use Monte Carlo for systems.": "二阶根不确定度目前仅支持标量实数根；方程组请使用 Monte Carlo。",
    "Second-order root uncertainty fell back to linear propagation: multiple uncertain inputs require mixed curvature terms.": "二阶根不确定度已回退到线性传播：多个不确定输入需要混合曲率项。",
    "Second-order root uncertainty fell back to linear propagation.": "二阶根不确定度已回退到线性传播。",
    "Monte Carlo root uncertainty is supported for scalar and system roots only.": "Monte Carlo 根不确定度目前仅支持标量根和方程组根。",
    "Monte Carlo root uncertainty skipped: sample budget exceeds the interactive worker limit.": "已跳过 Monte Carlo 根不确定度：样本预算超过交互式 worker 限制。",
    "Monte Carlo root uncertainty skipped: fewer than two valid samples.": "已跳过 Monte Carlo 根不确定度：有效样本少于两个。",
}


def localize_root_message(value: str, *, language: str) -> str:
    return ROOT_MESSAGE_ZH.get(value, value) if language == "zh" else value
