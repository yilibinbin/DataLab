"""
验证二阶误差传递修复的正确性
"""
from mpmath import mp
from data_extrapolation_latex_latest import error_propagation


def test_x_squared_mean_and_variance():
    """
    验证 f(x) = x^2 的均值和方差计算

    理论值（x ~ N(0, σ²)）：
    - E[x²] = σ²
    - Var[x²] = E[x⁴] - (E[x²])² = 3σ⁴ - σ⁴ = 2σ⁴
    """
    with mp.workdps(60):
        formula = "x**2"
        variables = ["x"]
        values = [mp.mpf("0")]
        sigmas = [mp.mpf("1")]

        # 二阶泰勒
        mean_taylor, std_taylor = error_propagation(
            formula, variables, values, sigmas,
            method="taylor", order=2
        )

        # 蒙特卡洛（大样本量）
        mean_mc, std_mc = error_propagation(
            formula, variables, values, sigmas,
            method="monte_carlo", mc_samples=100000, mc_seed=42
        )

        # 理论值
        theoretical_mean = mp.mpf("1")  # E[x²] = σ² = 1
        theoretical_std = mp.sqrt(2)     # sqrt(Var[x²]) = sqrt(2σ⁴) = sqrt(2)

        print("\nf(x) = x², x ~ N(0, 1)")
        print(f"理论均值: {theoretical_mean}")
        print(f"二阶泰勒均值: {mean_taylor}")
        print(f"蒙特卡洛均值: {mean_mc}")
        print("")
        print(f"理论标准差: {theoretical_std}")
        print(f"二阶泰勒标准差: {std_taylor}")
        print(f"蒙特卡洛标准差: {std_mc}")

        # 验证二阶泰勒与理论值一致
        assert mp.almosteq(mean_taylor, theoretical_mean, rel_eps=1e-10)
        assert mp.almosteq(std_taylor, theoretical_std, rel_eps=1e-10)

        # 蒙特卡洛应该在合理误差范围内
        assert mp.fabs(mean_mc - theoretical_mean) < 0.05
        assert mp.fabs(std_mc - theoretical_std) < 0.05


def test_nonlinear_function():
    """
    测试非线性函数 f(x, y) = x*y + x²
    """
    with mp.workdps(60):
        formula = "x*y + x**2"
        variables = ["x", "y"]
        x0, y0 = mp.mpf("1"), mp.mpf("2")
        sigma_x, sigma_y = mp.mpf("0.1"), mp.mpf("0.2")

        values = [x0, y0]
        sigmas = [sigma_x, sigma_y]

        # 计算解析导数
        # f = x*y + x²
        # ∂f/∂x = y + 2x = 2 + 2*1 = 4
        # ∂f/∂y = x = 1
        # ∂²f/∂x² = 2
        # ∂²f/∂y² = 0
        # ∂²f/∂x∂y = 1

        # 一阶方差：(4)² * (0.1)² + (1)² * (0.2)² = 0.16 + 0.04 = 0.20
        var_order1 = (4**2) * (0.1**2) + (1**2) * (0.2**2)

        # 二阶贡献：
        # - 对角项：1/2 * (2)² * (0.1²)² + 1/2 * (0)² * (0.2²)² = 0.00002
        # - 非对角项：2 * 1/2 * (1)² * (0.1)² * (0.2)² = 0.0004
        var_order2_contrib = (
            0.5 * (2**2) * (0.1**4) +
            0.5 * (0**2) * (0.2**4) +
            2 * 0.5 * (1**2) * (0.1**2) * (0.2**2)
        )

        expected_var_total = var_order1 + var_order2_contrib
        expected_std = mp.sqrt(expected_var_total)

        # 均值修正：1/2 * [2 * (0.1)² + 0 * (0.2)²] = 0.01
        expected_mean = x0 * y0 + x0**2 + 0.5 * 2 * (0.1**2)

        value1, std1 = error_propagation(formula, variables, values, sigmas,
                                         method="taylor", order=1)
        value2, std2 = error_propagation(formula, variables, values, sigmas,
                                         method="taylor", order=2)

        print("\nf(x, y) = x*y + x², x=1±0.1, y=2±0.2")
        print(f"一阶泰勒均值: {value1}")
        print(f"二阶泰勒均值: {value2} (期望: {expected_mean})")
        print(f"一阶泰勒标准差: {std1} (期望: {mp.sqrt(var_order1)})")
        print(f"二阶泰勒标准差: {std2} (期望: {expected_std})")

        # 验证
        assert mp.almosteq(value1, x0 * y0 + x0**2, rel_eps=1e-10)
        assert mp.almosteq(value2, expected_mean, rel_eps=1e-8)
        assert mp.almosteq(std1, mp.sqrt(var_order1), rel_eps=1e-8)
        assert mp.almosteq(std2, expected_std, rel_eps=1e-8)


def test_comparison_with_monte_carlo():
    """
    对比二阶泰勒和蒙特卡洛在不同非线性程度下的表现
    """
    test_cases = [
        ("x + y", "线性函数"),
        ("x * y", "双线性函数"),
        ("x**2 + y**2", "二次函数"),
        ("x**2 * y", "混合非线性"),
    ]

    with mp.workdps(60):
        x0, y0 = mp.mpf("1"), mp.mpf("1")
        sigma_x, sigma_y = mp.mpf("0.1"), mp.mpf("0.1")

        print("\n" + "="*60)
        print("二阶泰勒 vs 蒙特卡洛对比")
        print("="*60)

        for formula, desc in test_cases:
            values = [x0, y0]
            sigmas = [sigma_x, sigma_y]
            variables = ["x", "y"]

            mean_t2, std_t2 = error_propagation(
                formula, variables, values, sigmas,
                method="taylor", order=2
            )

            mean_mc, std_mc = error_propagation(
                formula, variables, values, sigmas,
                method="monte_carlo", mc_samples=50000, mc_seed=123
            )

            print(f"\n{desc}: {formula}")
            print(f"  均值 - 泰勒: {float(mean_t2):.6f}, MC: {float(mean_mc):.6f}, 差异: {float(abs(mean_t2 - mean_mc)):.6f}")
            print(f"  标准差 - 泰勒: {float(std_t2):.6f}, MC: {float(std_mc):.6f}, 差异: {float(abs(std_t2 - std_mc)):.6f}")

            # 对于线性和二次函数，二阶泰勒应该非常准确
            if "线性" in desc or "二次" in desc:
                assert mp.fabs(mean_t2 - mean_mc) < 0.01
                assert mp.fabs(std_t2 - std_mc) < 0.01


if __name__ == "__main__":
    test_x_squared_mean_and_variance()
    test_nonlinear_function()
    test_comparison_with_monte_carlo()
    print("\n" + "="*60)
    print("所有验证测试通过！✓")
    print("="*60)
