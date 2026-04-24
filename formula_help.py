#!/usr/bin/env python3
"""
Shared formula help and extrapolation method documentation.
Single source of truth for function lists, syntax help, and method descriptions.
Used by both desktop GUI and web interface to ensure consistency.
"""

# ============================================================
# Function Support Documentation
# ============================================================

FUNCTION_HELP_ZH = """可用函数（Mathematica 风格首字母大写，使用 f[x] 语法）：

基本三角函数：
  Sin Cos Tan Asin Acos Atan Sinh Cosh Tanh Asinh Acosh Atanh

指数与对数：
  Exp Log Ln Log10 Power Sqrt

特殊函数：
  Abs Erf Gamma Zeta
  Hyp0f1 Hyp1f1 Hyp2f1 PolyLog
  BesselJ BesselY Airy

数学常数：
  Pi, E

语法规则：
  • 使用方括号：Sin[x], Cos[x^2], Exp[-x]
  • 支持幂运算：^ 或 **（例如 x^2 或 x**2）
  • 支持列名、A/B/C 或 x1/x2/x3 作为变量
  • 支持复杂表达式：Sin[x]^2 + Cos[x]^2

示例：
  • Sin[x]^2 + Zeta[3]
  • Hyp2f1[1/2, 1, 3/2, x]
  • Exp[-x^2]*Sin[Pi*x]
  • (C - B)^2/(B - A) + C
"""

FUNCTION_HELP_EN = """Available functions (Mathematica style, capitalized, use f[x]):

Basic Trigonometric:
  Sin Cos Tan Asin Acos Atan Sinh Cosh Tanh Asinh Acosh Atanh

Exponential & Logarithmic:
  Exp Log Ln Log10 Power Sqrt

Special Functions:
  Abs Erf Gamma Zeta
  Hyp0f1 Hyp1f1 Hyp2f1 PolyLog
  BesselJ BesselY Airy

Mathematical Constants:
  Pi, E

Syntax Rules:
  • Use square brackets: Sin[x], Cos[x^2], Exp[-x]
  • Power operators: ^ or ** (e.g., x^2 or x**2)
  • Variables: column names, A/B/C, or x1/x2/x3
  • Complex expressions: Sin[x]^2 + Cos[x]^2

Examples:
  • Sin[x]^2 + Zeta[3]
  • Hyp2f1[1/2, 1, 3/2, x]
  • Exp[-x^2]*Sin[Pi*x]
  • (C - B)^2/(B - A) + C
"""

FUNCTION_TOOLTIP_ZH = (
    "可用函数（Mathematica 风格首字母大写，使用 f[x] 语法）：\n"
    "基本：Sin Cos Tan Asin Acos Atan Sinh Cosh Tanh Asinh Acosh Atanh\n"
    "指数/对数：Exp Log Ln Log10 Power Sqrt\n"
    "特殊：Abs Erf Gamma Zeta Hyp0f1 Hyp1f1 Hyp2f1 PolyLog BesselJ BesselY Airy\n"
    "常数：Pi, E\n"
    "示例：Sin[x]^2 + Zeta[3]， Hyp2f1[1/2,1,3/2,x]"
)

FUNCTION_TOOLTIP_EN = (
    "Available functions (Mathematica style, capitalized, use f[x]):\n"
    "Basic: Sin Cos Tan Asin Acos Atan Sinh Cosh Tanh Asinh Acosh Atanh\n"
    "Exponential/Log: Exp Log Ln Log10 Power Sqrt\n"
    "Special: Abs Erf Gamma Zeta Hyp0f1 Hyp1f1 Hyp2f1 PolyLog BesselJ BesselY Airy\n"
    "Constants: Pi, E\n"
    "Example: Sin[x]^2 + Zeta[3],  Hyp2f1[1/2,1,3/2,x]"
)


# ============================================================
# Extrapolation Method Documentation
# ============================================================

EXTRAPOLATION_METHODS = {
    "power_law": {
        "name_zh": "幂律外推(三点外推)",
        "name_en": "Power law (3-point)",
        "description_zh": """幂律外推（三点外推）

适用场景：
  • 数据呈幂律收敛趋势：f(x) ≈ f∞ + A·x^(-p)
  • 物理量随参数变化趋于极限值
  • 需要至少 3 个数据点

参数说明：
  • x1, x2, x3：三个自变量值（如网格大小、时间步长等）
  • p（可选）：幂指数，留空则自动求解
  • 初始猜测：用于优化算法的起始值

注意事项：
  • 要求数据单调收敛
  • 对噪声敏感，建议数据较为干净
  • x 值应足够分散以避免数值不稳定""",
        "description_en": """Power Law Extrapolation (3-point)

Applicable for:
  • Data showing power-law convergence: f(x) ≈ f∞ + A·x^(-p)
  • Physical quantities approaching a limit
  • Requires at least 3 data points

Parameters:
  • x1, x2, x3: Three x-values (grid sizes, time steps, etc.)
  • p (optional): Power exponent, auto-solved if blank
  • Initial guess: Starting value for optimization

Cautions:
  • Requires monotonic convergence
  • Sensitive to noise; works best with clean data
  • x-values should be well-separated""",
        "parameters": [
            {"name": "x1", "type": "float", "default": "10", "description_zh": "第一个 x 值", "description_en": "First x value"},
            {"name": "x2", "type": "float", "default": "20", "description_zh": "第二个 x 值", "description_en": "Second x value"},
            {"name": "x3", "type": "float", "default": "40", "description_zh": "第三个 x 值", "description_en": "Third x value"},
            {"name": "p", "type": "float", "optional": True, "description_zh": "幂指数（留空自动求解）", "description_en": "Power exponent (auto if blank)"},
            {"name": "initial_guess", "type": "float", "default": "1.0", "description_zh": "初始猜测值", "description_en": "Initial guess"},
        ],
    },
    "richardson": {
        "name_zh": "Richardson 序列加速(三点外推)",
        "name_en": "Richardson (3-point)",
        "description_zh": """Richardson 序列加速

适用场景：
  • 误差展开形式已知：f(h) ≈ f∞ + c₁h^p₁ + c₂h^p₂ + ...
  • 数值积分、微分的Richardson外推
  • 有限差分方法的精度提升

方法原理：
  • 利用不同步长的结果构造更高阶的近似
  • 消除误差展开的前导项
  • 基于已知的收敛幂指数 p

参数说明：
  • p（收敛幂指数）：误差展开中的幂指数，默认 p=2
    - p=2：二阶收敛方法（最常见）
    - p=4：四阶收敛方法
    - 其他值：根据具体问题确定

注意事项：
  • 需要准确知道误差阶数 p
  • 要求误差展开形式规则
  • 步长应成一定比例关系
  • 错误的 p 值会导致外推失败""",
        "description_en": """Richardson Extrapolation

Applicable for:
  • Known error expansion: f(h) ≈ f∞ + c₁h^p₁ + c₂h^p₂ + ...
  • Numerical integration/differentiation
  • Finite difference accuracy improvement

Method:
  • Constructs higher-order approximations from different step sizes
  • Eliminates leading error terms
  • Based on known convergence power p

Parameters:
  • p (convergence power): Power exponent in error expansion, default p=2
    - p=2: Second-order convergence (most common)
    - p=4: Fourth-order convergence
    - Other values: Problem-specific

Cautions:
  • Requires accurate knowledge of error order p
  • Needs regular error expansion
  • Step sizes should be in proportion
  • Wrong p value will cause extrapolation to fail""",
        "parameters": [
            {
                "name": "p",
                "type": "float",
                "default": "2.0",
                "range": "0.1-10.0",
                "description_zh": "收敛幂指数（误差 ∝ h^p）",
                "description_en": "Convergence power (error ∝ h^p)",
            },
        ],
    },
    "shanks": {
        "name_zh": "Shanks 变换",
        "name_en": "Shanks transform",
        "description_zh": """Shanks 变换（非线性序列变换）

适用场景：
  • 线性收敛或对数收敛的序列加速
  • 部分和序列的加速收敛
  • 迭代算法的加速

方法原理：
  • 基于部分和的比值关系
  • 构造新序列以加速收敛
  • 等价于 Padé 逼近的对角线序列

注意事项：
  • 对振荡序列效果有限
  • 需要足够多的序列项（至少3项）
  • 可能产生不规则跳变""",
        "description_en": """Shanks Transform (Nonlinear Sequence Transform)

Applicable for:
  • Linearly or logarithmically convergent sequences
  • Accelerating partial sums
  • Iterative algorithm speedup

Method:
  • Based on ratio relations of partial sums
  • Constructs new sequence with faster convergence
  • Equivalent to diagonal Padé sequence

Cautions:
  • Limited effectiveness for oscillating sequences
  • Requires sufficient terms (at least 3)
  • May produce irregular jumps""",
        "parameters": [],
    },
    "levin_u": {
        "name_zh": "Levin u-transform",
        "name_en": "Levin u-transform",
        "description_zh": """Levin u 变换（序列加速方法）

适用场景：
  • 交替级数或振荡序列
  • 对数收敛或缓慢收敛的序列
  • 渐近展开的求和

方法原理：
  • 利用序列的"余项"信息构造加速序列
  • 对交替序列特别有效
  • 可调整变换阶数以适应不同收敛速度
  • 支持自定义权重函数以优化收敛

参数说明：
  • variant：变换类型（u/t/v，默认u）
    - u：最常用，适用于大多数序列
    - t：专门用于级数求和
    - v：专门用于积分加速

  • 阶数（order）：控制变换的复杂度
    - 阶数越高，精度越高，但需要更多数据点
    - 需要至少 2N+1 项数据（N = 阶数）
    - 推荐从 2 开始

  • 权重函数（weight）：
    - 默认 (1)：标准权重
    - 1/(n+1)：倒数权重，适用于快速收敛序列
    - 1/(n+β)：可调节倒数权重，β 可自定义

注意事项：
  • 需要至少 2N+1 项（N为变换阶数）
  • 对严重振荡序列可能失效
  • 权重选择会显著影响结果
  • 建议先用默认参数，再根据效果调整""",
        "description_en": """Levin u-transform (Sequence Acceleration)

Applicable for:
  • Alternating or oscillating sequences
  • Logarithmically or slowly convergent sequences
  • Asymptotic expansion summation

Method:
  • Uses sequence "remainder" information
  • Particularly effective for alternating series
  • Adjustable order for different convergence rates
  • Supports custom weight functions for optimized convergence

Parameters:
  • variant: Transform type (u/t/v, default u)
    - u: Most common, suitable for most sequences
    - t: Specialized for series summation
    - v: Specialized for integral acceleration

  • order: Controls transform complexity
    - Higher order = higher accuracy, but needs more data points
    - Requires at least 2N+1 data points (N = order)
    - Recommended to start with 2

  • weight function:
    - Default (1): Standard weight
    - 1/(n+1): Reciprocal weight, for fast-converging sequences
    - 1/(n+β): Adjustable reciprocal weight with customizable β

Cautions:
  • Requires at least 2N+1 terms (N = order)
  • May fail for severely oscillating sequences
  • Weight choice significantly affects results
  • Recommend starting with default parameters, then adjust based on results""",
        "parameters": [
            {
                "name": "variant",
                "type": "select",
                "options": ["u", "t", "v"],
                "default": "u",
                "description_zh": "变换类型（u最常用，t适用于级数，v用于积分）",
                "description_en": "Transform type (u most common, t for series, v for integrals)",
            },
            {
                "name": "order",
                "type": "int",
                "default": 2,
                "min": 1,
                "max": 10,
                "description_zh": "变换阶数（越高越精确但需要更多项）",
                "description_en": "Transform order (higher = more accurate but needs more terms)",
            },
            {
                "name": "weight",
                "type": "select",
                "options": ["default", "reciprocal", "reciprocal_beta"],
                "default": "default",
                "description_zh": "权重函数类型",
                "description_en": "Weight function type",
            },
            {
                "name": "beta",
                "type": "float",
                "default": 1.0,
                "range": "0.01-100.0",
                "optional": True,
                "description_zh": "β参数（仅当权重为 1/(n+β) 时有效）",
                "description_en": "β parameter (only effective when weight is 1/(n+β))",
            },
        ],
    },
    "wynn_epsilon": {
        "name_zh": "Wynn-epsilon 算法",
        "name_en": "Wynn-epsilon algorithm",
        "description_zh": """Wynn-epsilon 算法（迭代加速方法）

适用场景：
  • 线性收敛序列的加速
  • Shanks 变换的稳定数值实现
  • 部分和序列或迭代序列

方法原理：
  • 使用 epsilon 算法的递推公式
  • 数值稳定的 Padé 逼近计算
  • 逐步构造加速序列

注意事项：
  • 对振荡序列不如 Levin 变换
  • 可能出现数值不稳定（除零）
  • 需要监控中间结果的合理性""",
        "description_en": """Wynn-epsilon Algorithm (Iterative Acceleration)

Applicable for:
  • Linearly convergent sequences
  • Numerically stable Shanks transform
  • Partial sum or iterative sequences

Method:
  • Uses epsilon algorithm recursion
  • Numerically stable Padé approximation
  • Progressively constructs accelerated sequence

Cautions:
  • Less effective than Levin for oscillating sequences
  • May encounter numerical instability (division by zero)
  • Monitor intermediate results for validity""",
        "parameters": [],
    },
    "custom": {
        "name_zh": "自定义公式(三点外推)",
        "name_en": "Custom (3-point)",
        "description_zh": """自定义公式外推

适用场景：
  • 已知特定的外推公式
  • 需要基于物理模型的自定义计算
  • 标准方法不适用时的灵活方案

公式语法：
  • 使用 A, B, C 代表三列数据（或列名、x1/x2/x3）
  • 支持所有数学函数（见函数支持）
  • 支持复杂表达式组合

示例公式：
  • (C - B)^2/(B - A) + C  （Richardson风格）
  • Exp[-x1]*Sin[x2] + C  （自定义模型）
  • Log[C/B]/Log[B/A]     （对数外推）

注意事项：
  • 公式需确保数学上有意义
  • 避免除零、负数开方等非法运算
  • 建议先用简单数据测试公式""",
        "description_en": """Custom Formula Extrapolation

Applicable for:
  • Known specific extrapolation formula
  • Physics-based custom calculations
  • Flexible solution when standard methods don't apply

Formula Syntax:
  • Use A, B, C for three data columns (or column names, x1/x2/x3)
  • Supports all mathematical functions (see function support)
  • Supports complex expression combinations

Example Formulas:
  • (C - B)^2/(B - A) + C  (Richardson style)
  • Exp[-x1]*Sin[x2] + C  (Custom model)
  • Log[C/B]/Log[B/A]     (Logarithmic extrapolation)

Cautions:
  • Formula must be mathematically valid
  • Avoid division by zero, negative square roots
  • Test formula with simple data first""",
        "parameters": [],
    },
}


def get_function_help(lang: str = "zh") -> str:
    """Get function help text in specified language."""
    return FUNCTION_HELP_ZH if lang == "zh" else FUNCTION_HELP_EN


def get_function_tooltip(lang: str = "zh") -> str:
    """Get function tooltip text in specified language."""
    return FUNCTION_TOOLTIP_ZH if lang == "zh" else FUNCTION_TOOLTIP_EN


def get_method_description(method_key: str, lang: str = "zh") -> str:
    """Get extrapolation method description."""
    if method_key not in EXTRAPOLATION_METHODS:
        return ""
    method = EXTRAPOLATION_METHODS[method_key]
    return method.get(f"description_{lang}", "")


def get_method_name(method_key: str, lang: str = "zh") -> str:
    """Get extrapolation method display name."""
    if method_key not in EXTRAPOLATION_METHODS:
        return method_key
    method = EXTRAPOLATION_METHODS[method_key]
    return method.get(f"name_{lang}", method_key)


def get_method_parameters(method_key: str) -> list[dict]:
    """Get parameter definitions for a method."""
    if method_key not in EXTRAPOLATION_METHODS:
        return []
    return EXTRAPOLATION_METHODS[method_key].get("parameters", [])
