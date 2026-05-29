"""Phase 6 #28 — OpenAPI spec regression tests.

Pins the spec's completeness and structural correctness.
"""

from __future__ import annotations

import json

import pytest


def test_build_spec_returns_openapi_3():
    from app_web.openapi import OPENAPI_VERSION, build_spec

    spec = build_spec()
    assert spec["openapi"] == OPENAPI_VERSION
    assert OPENAPI_VERSION.startswith("3.")


def test_spec_has_info_block():
    from app_web.openapi import build_spec

    spec = build_spec(app_version="2.0.0-dev")
    assert "info" in spec
    info = spec["info"]
    assert info["title"]
    assert info["version"] == "2.0.0-dev"
    assert info["description"]


def test_spec_servers_block_uses_injected_url():
    from app_web.openapi import build_spec

    spec = build_spec(server_url="https://datalab.example/")
    assert spec["servers"][0]["url"] == "https://datalab.example/"


def test_spec_has_core_endpoints():
    from app_web.openapi import build_spec

    spec = build_spec()
    paths = spec["paths"]
    required = [
        "/api/health",
        "/api/ui-specs",
        "/api/extrapolate",
        "/api/fit",
        "/api/error-propagation",
        "/api/spec.json",
    ]
    for p in required:
        assert p in paths, f"missing endpoint: {p}"


def test_endpoints_declare_methods():
    from app_web.openapi import build_spec

    spec = build_spec()
    for path, operations in spec["paths"].items():
        assert operations, f"path {path} has no operations"
        for method, op in operations.items():
            assert method in ("get", "post", "put", "delete", "patch"), (
                f"unknown method {method} for {path}"
            )
            assert "summary" in op, f"{method.upper()} {path} missing summary"
            assert "responses" in op, f"{method.upper()} {path} missing responses"


def test_post_endpoints_have_request_body():
    from app_web.openapi import build_spec

    spec = build_spec()
    post_paths = [
        path for path, ops in spec["paths"].items() if "post" in ops
    ]
    for path in post_paths:
        post_op = spec["paths"][path]["post"]
        assert "requestBody" in post_op, f"POST {path} missing requestBody"
        rb = post_op["requestBody"]
        assert rb.get("required") is True, f"POST {path} requestBody must be required"
        assert "application/json" in rb["content"]


def test_responses_reference_schemas():
    """Every response body should either be an inline schema or a
    $ref to ``#/components/schemas/...``."""
    from app_web.openapi import build_spec

    spec = build_spec()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            for status, resp in op["responses"].items():
                if "content" not in resp:
                    continue
                for mime, body in resp["content"].items():
                    assert "schema" in body, (
                        f"{method.upper()} {path} {status} "
                        f"{mime} missing schema"
                    )


def test_component_schemas_present():
    from app_web.openapi import build_spec

    spec = build_spec()
    schemas = spec["components"]["schemas"]
    for name in ("ErrorResponse", "UISpec", "FitResult", "ExtrapolationResult"):
        assert name in schemas, f"component schema {name} missing"


def test_error_response_schema_has_error_field():
    from app_web.openapi import build_spec

    spec = build_spec()
    error = spec["components"]["schemas"]["ErrorResponse"]
    assert "error" in error["required"]


def test_fit_result_has_params_object():
    from app_web.openapi import build_spec

    spec = build_spec()
    fit = spec["components"]["schemas"]["FitResult"]
    props = fit["properties"]
    for field in ("model", "params", "param_errors_stat", "aic", "bic", "r2"):
        assert field in props, f"FitResult.{field} missing"


def test_extrapolate_declares_method_enum():
    from app_web.openapi import build_spec

    spec = build_spec()
    schema = (
        spec["paths"]["/api/extrapolate"]["post"]
        ["requestBody"]["content"]["application/json"]["schema"]
    )
    method_enum = schema["properties"]["method"]["enum"]
    for required in ("richardson", "wynn_epsilon", "power_law"):
        assert required in method_enum


def test_fit_precision_has_bounds():
    """Precision must be bounded at the API layer for DoS defence."""
    from app_web.openapi import build_spec

    spec = build_spec()
    schema = (
        spec["paths"]["/api/fit"]["post"]
        ["requestBody"]["content"]["application/json"]["schema"]
    )
    precision = schema["properties"]["precision"]
    assert precision["minimum"] >= 10
    assert precision["maximum"] <= 1000


def test_spec_is_json_serialisable():
    """The spec dict must round-trip through json.dumps — otherwise
    the /api/spec.json endpoint can't return it."""
    from app_web.openapi import build_spec

    spec = build_spec(app_version="2.0.0-dev", server_url="https://x.y/")
    encoded = json.dumps(spec, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded == spec


def test_tags_used_by_operations_are_declared():
    """Every tag referenced in an operation must be declared in the
    top-level ``tags`` list — otherwise Swagger UI renders them as
    orphans."""
    from app_web.openapi import build_spec

    spec = build_spec()
    declared = {t["name"] for t in spec.get("tags", [])}
    used: set[str] = set()
    for ops in spec["paths"].values():
        for op in ops.values():
            used.update(op.get("tags", []))
    missing = used - declared
    assert not missing, f"undeclared tags: {missing}"


def test_spec_version_defaults_to_unknown():
    from app_web.openapi import build_spec

    spec = build_spec()
    assert spec["info"]["version"] == "unknown"
