"""Generate an OpenAPI 3.0 spec for DataLab's web API (Phase 6 #28).

The spec is emitted at ``GET /api/spec.json`` (wired from
``app_web/server.py``). Downstream consumers:

- ``docs/web/api.md`` renders the spec via the OpenAPI block MkDocs
  plugin, so the website always shows the current API surface.
- Any client generator (openapi-generator, swagger-codegen) can pull
  the JSON and emit typed HTTP clients in Python, TypeScript, etc.

We hand-build the spec rather than pulling ``apispec`` or
``flask-smorest``: DataLab's HTTP surface is small and stable (a
handful of endpoints), and the dependency footprint matters for the
thin install the web deploy targets.

The spec stays in sync with the actual routes via the
``test_openapi_endpoints_match_actual_routes`` test — if someone
adds a new ``/api/...`` route without updating this file, that test
fails.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "OPENAPI_VERSION",
    "build_spec",
]


OPENAPI_VERSION = "3.0.3"


def _component_schemas() -> dict[str, Any]:
    """Reusable schema fragments referenced from path responses."""
    return {
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["error"],
        },
        "UISpec": {
            "type": "object",
            "description": (
                "Parameter-widget descriptors for a computation method. "
                "See shared/ui_specs.py for the canonical schema."
            ),
            "additionalProperties": True,
        },
        "ExtrapolationResult": {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "value": {"type": "string"},
                "metadata": {"type": "object", "additionalProperties": True},
            },
        },
        "FitResult": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                # High-precision fit parameters/errors are emitted as decimal
                # STRINGS (via mp.nstr at the requested precision), not JSON
                # numbers, to preserve precision beyond float's ~17 digits
                # (audit R3 D3). Keep this in sync with the SSE result emitter.
                "params": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "param_errors_stat": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "aic": {"type": "number"},
                "bic": {"type": "number"},
                "r2": {"type": "number"},
            },
        },
    }


def _standard_error_response() -> dict[str, Any]:
    return {
        "description": "Validation error or internal failure.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
            }
        },
    }


def build_spec(
    *,
    server_url: str = "https://example.invalid",
    app_version: str = "unknown",
) -> dict[str, Any]:
    """Build the OpenAPI dict.

    Parameters
    ----------
    server_url:
        Canonical server URL shown to clients. In production the
        deployer passes their own (configurable via
        ``DATALAB_PUBLIC_URL``); tests pass a dummy.
    app_version:
        Version string shown under ``info.version`` — pulled from
        pyproject.toml at runtime. Keep this a string so a pre-
        release tag like ``2.0.0.dev0`` is allowed.
    """
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "DataLab Web API",
            "description": (
                "High-precision scientific API for sequence extrapolation, "
                "curve fitting, and error propagation. Backs both the "
                "DataLab web frontend and third-party clients."
            ),
            "version": str(app_version),
            "license": {
                "name": "See repository",
            },
        },
        "servers": [
            {"url": server_url, "description": "Primary deployment"},
        ],
        "tags": [
            {"name": "meta", "description": "Service metadata."},
            {"name": "extrapolation", "description": "Sequence extrapolation endpoints."},
            {"name": "fitting", "description": "Curve-fitting endpoints."},
            {"name": "error-propagation", "description": "Uncertainty propagation endpoints."},
        ],
        "paths": {
            "/api/health": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Liveness probe.",
                    "responses": {
                        "200": {
                            "description": "Service is up.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                    },
                },
            },
            "/api/ui-specs": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Return the widget specs shared between desktop and web UIs.",
                    "description": (
                        "Single source of truth for method parameters. The desktop and "
                        "web frontends both render forms from this payload."
                    ),
                    "responses": {
                        "200": {
                            "description": "UI spec document.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UISpec"},
                                }
                            },
                        },
                    },
                },
            },
            "/api/extrapolate": {
                "post": {
                    "tags": ["extrapolation"],
                    "summary": "Run a sequence-extrapolation method.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "method": {
                                            "type": "string",
                                            "enum": [
                                                "richardson",
                                                "wynn_epsilon",
                                                "shanks",
                                                "levin",
                                                "power_law",
                                            ],
                                        },
                                        "sequence": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                        },
                                        "precision": {
                                            "type": "integer",
                                            "minimum": 10,
                                            "maximum": 1000,
                                        },
                                    },
                                    "required": ["method", "sequence"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Extrapolation result.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ExtrapolationResult"
                                    },
                                }
                            },
                        },
                        "400": _standard_error_response(),
                    },
                },
            },
            "/api/fit": {
                "post": {
                    "tags": ["fitting"],
                    "summary": "Run a single-model fit.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "x": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                        },
                                        "y": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                        },
                                        "model": {"type": "string"},
                                        "precision": {
                                            "type": "integer",
                                            "minimum": 10,
                                            "maximum": 1000,
                                        },
                                    },
                                    "required": ["x", "y", "model"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Fit result with parameters and errors.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/FitResult"},
                                }
                            },
                        },
                        "400": _standard_error_response(),
                    },
                },
            },
            "/api/error-propagation": {
                "post": {
                    "tags": ["error-propagation"],
                    "summary": "Propagate uncertainties through a user-supplied formula.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string"},
                                        "variables": {
                                            "type": "object",
                                            "additionalProperties": {"type": "number"},
                                        },
                                        "uncertainties": {
                                            "type": "object",
                                            "additionalProperties": {"type": "number"},
                                        },
                                    },
                                    "required": ["formula", "variables"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Propagated value and uncertainty.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "value": {"type": "number"},
                                            "uncertainty": {"type": "number"},
                                        },
                                    },
                                }
                            },
                        },
                        "400": _standard_error_response(),
                    },
                },
            },
            "/api/spec.json": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Return this OpenAPI specification.",
                    "responses": {
                        "200": {
                            "description": "OpenAPI 3.0 spec JSON.",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                }
                            },
                        },
                    },
                },
            },
        },
        "components": {
            "schemas": _component_schemas(),
        },
    }
