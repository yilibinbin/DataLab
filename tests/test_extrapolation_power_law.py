from __future__ import annotations

from mpmath import mp

from data_extrapolation_latex_latest import ExtrapolationOptions, process_data_string
from extrapolation_methods.power_law import PowerLawConfig, extrapolate_power_law


def test_power_law_known_exact_case():
    # E(x) = E_inf + A*x^(-p) with known exact parameters.
    with mp.workdps(80):
        E_inf = mp.mpf("10")
        A = mp.mpf("5")
        p = mp.mpf("2")
        x1, x2, x3 = mp.mpf("3"), mp.mpf("4"), mp.mpf("5")
        E1 = E_inf + A * mp.power(x1, -p)
        E2 = E_inf + A * mp.power(x2, -p)
        E3 = E_inf + A * mp.power(x3, -p)

        config = PowerLawConfig(x_values=[x1, x2, x3], precision=80, initial_guess=p)
        result = extrapolate_power_law(config, [E1, E2, E3])

        assert mp.almosteq(result.value, E_inf, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result.exponent, p, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result.amplitude, A, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))


def test_power_law_uncertainty_reference_and_auto_max_diff():
    with mp.workdps(80):
        E_inf = mp.mpf("10")
        A = mp.mpf("5")
        p = mp.mpf("2")
        x1, x2, x3 = mp.mpf("3"), mp.mpf("4"), mp.mpf("5")
        E1 = E_inf + A * mp.power(x1, -p)
        E2 = E_inf + A * mp.power(x2, -p)
        E3 = E_inf + A * mp.power(x3, -p)

        data_text = f"A B C\n{mp.nstr(E1, 50)} {mp.nstr(E2, 50)} {mp.nstr(E3, 50)}\n"
        power_cfg = PowerLawConfig(x_values=[x1, x2, x3], precision=80, initial_guess=p)

        opts_default = ExtrapolationOptions(method="power_law", power_law_config=power_cfg, mp_precision=80)
        headers, rows, results = process_data_string(data_text, verbose=False, options=opts_default)
        assert headers == ["A", "B", "C"]
        assert rows
        assert results
        res = results[0]
        assert mp.almosteq(res.value, E_inf, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert res.details.get("reference_column") == "C"
        assert mp.almosteq(res.uncertainty, mp.fabs(res.value - E3), rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))

        opts_auto = ExtrapolationOptions(
            method="power_law",
            power_law_config=power_cfg,
            mp_precision=80,
            uncertainty_column="auto_max_diff",
        )
        _, _, results_auto = process_data_string(data_text, verbose=False, options=opts_auto)
        res_auto = results_auto[0]
        assert res_auto.details.get("reference_column") == "A"
        assert mp.almosteq(
            res_auto.uncertainty,
            mp.fabs(res_auto.value - E1),
            rel_eps=mp.mpf("1e-40"),
            abs_eps=mp.mpf("1e-40"),
        )
