"""Every /api route must require a token.

This is the guard that /api/current-user needed and did not have: it sat
unauthenticated among 47 routes that were not, and nothing failed. Adding a route
without the dependency now breaks this test, which forces the decision to be
deliberate rather than silent.
"""

import main
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# The only two routes that legitimately take no token: you cannot hold one yet.
# Both are rate-limited in main.py (5/hour and 10/minute) since they are reachable
# by anyone. Adding to this list should be a conscious act, reviewed as such.
PUBLIC_ROUTES = {
    "/api/register-user",
    "/api/login-user",
}


def _api_routes():
    return [
        route for route in main.app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
    ]


def test_there_are_api_routes_to_check():
    # Guards against the inventory test passing vacuously if the import or the
    # route-filtering predicate ever breaks.
    assert len(_api_routes()) > 40


@pytest.mark.parametrize("route", _api_routes(), ids=lambda r: r.path)
def test_api_route_requires_authentication(route):
    if route.path in PUBLIC_ROUTES:
        return

    dependencies = [d.call for d in route.dependant.dependencies]
    assert main.ensure_user_context in dependencies, (
        f"{route.path} has no ensure_user_context dependency, so it is reachable "
        f"without a token. Add Depends(ensure_user_context), or add the path to "
        f"PUBLIC_ROUTES in this test if it is genuinely meant to be public."
    )


def test_public_routes_all_exist():
    paths = {route.path for route in _api_routes()}
    assert PUBLIC_ROUTES <= paths, (
        f"PUBLIC_ROUTES names routes that no longer exist: {PUBLIC_ROUTES - paths}"
    )


def test_current_user_endpoint_is_gone():
    """Removed rather than authenticated - it only ever echoed the caller's own id."""
    assert "/api/current-user" not in {route.path for route in _api_routes()}
    assert TestClient(main.app).get("/api/current-user").status_code == 404


def test_authenticated_route_rejects_a_missing_token():
    # 401, not 403: FastAPI's HTTPBearer returns HTTP_401_UNAUTHORIZED with a
    # WWW-Authenticate header. Older versions returned 403 and much of the
    # documentation still says so.
    response = TestClient(main.app).get("/api/get-projects/")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_authenticated_route_rejects_a_malformed_token(jwt_keys):
    response = TestClient(main.app).get(
        "/api/get-projects/", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
