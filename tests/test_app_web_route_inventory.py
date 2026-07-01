from __future__ import annotations

from app_web.server import create_app


EXPECTED_ROUTES = (
    ("/", ("GET", "POST"), "pages.index"),
    ("/api/auto-fit/stream", ("GET",), "sse.auto_fit_stream"),
    ("/api/fit/stream", ("GET",), "sse.fit_stream"),
    ("/api/formula-preview", ("GET",), "api.api_formula_preview"),
    ("/api/function-help", ("GET",), "api.api_function_help"),
    ("/api/help_specs", ("GET",), "api.api_help_specs"),
    ("/api/method-help/<method_key>", ("GET",), "api.api_method_help"),
    ("/api/ui-specs", ("GET",), "api.api_ui_specs"),
    ("/docs", ("GET",), "docs.docs_index_redirect"),
    ("/docs-site", ("GET",), "docs.docs_site"),
    ("/docs-site/", ("GET",), "docs.docs_site"),
    ("/docs-site/<path:filename>", ("GET",), "docs.docs_site"),
    ("/docs/", ("GET",), "docs.docs_index"),
    ("/docs/<page>", ("GET",), "docs.docs_page"),
    ("/docs/<page>/", ("GET",), "docs.docs_page"),
    ("/error", ("GET", "POST"), "pages.error"),
    ("/fit", ("GET", "POST"), "pages.fit"),
    ("/roots", ("GET", "POST"), "pages.root_solving"),
    ("/stats", ("GET", "POST"), "pages.stats"),
)


def test_plain_flask_app_route_inventory_matches_phase0_baseline() -> None:
    app = create_app()

    routes = tuple(
        sorted(
            (
                rule.rule,
                tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})),
                rule.endpoint,
            )
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
        )
    )

    assert routes == EXPECTED_ROUTES
