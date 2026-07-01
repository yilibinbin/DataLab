from __future__ import annotations

import pytest

pytest.importorskip("flask")

from app_web.security import generate_csrf_token
from app_web.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _csrf_token(client) -> str:
    token = generate_csrf_token()
    with client.session_transaction() as session:
        session["csrf_token"] = token
    return token


def _post(client, path: str, data: dict[str, str]):
    payload = {"csrf_token": _csrf_token(client)}
    payload.update(data)
    return client.post(path, data=payload)


def test_roots_get_renders_form(client):
    resp = client.get("/roots")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'name="root_equations"' in html
    assert 'name="root_unknowns"' in html
    assert 'name="csrf_token"' in html


def test_nav_includes_root_solving_link(client):
    html = client.get("/roots").get_data(as_text=True)
    # The nav link is present and reachable at the /roots route.
    assert 'href="/roots"' in html
    assert 'data-i18n="nav.rootSolving"' in html


def test_roots_scalar_solve_returns_sqrt_two(client):
    resp = _post(
        client,
        "/roots",
        {
            "root_equations": "x**2 - 2",
            "root_unknowns": "x = 1",
            "root_mode": "scalar",
            "root_uncertainty_method": "off",
        },
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # The solved root of x**2 - 2 near guess 1 is +sqrt(2) ≈ 1.4142.
    assert "1.4142" in html


def test_roots_system_solve_returns_both_unknowns(client):
    resp = _post(
        client,
        "/roots",
        {
            "root_equations": "x + y - 3\nx - y - 1",
            "root_unknowns": "x = 0\ny = 0",
            "root_mode": "system",
            "root_uncertainty_method": "off",
        },
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # System solution: x = 2, y = 1.
    assert "2.0" in html
    assert "1.0" in html


def test_roots_missing_equations_flashes_error(client):
    resp = _post(
        client,
        "/roots",
        {"root_equations": "", "root_unknowns": "x = 1"},
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "errors.missing_equations" in html
