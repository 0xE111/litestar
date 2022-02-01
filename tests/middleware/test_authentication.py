import pytest
from pydantic import BaseModel
from starlette.requests import HTTPConnection
from starlette.status import (
    HTTP_200_OK,
    HTTP_403_FORBIDDEN,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from starlette.websockets import WebSocketDisconnect

from starlite import Starlite, create_test_client, get, websocket
from starlite.connection import Request, WebSocket
from starlite.exceptions import PermissionDeniedException
from starlite.middleware import AbstractAuthenticationMiddleware, AuthenticationResult


class User(BaseModel):
    name: str
    id: int


class Auth(BaseModel):
    props: str


user = User(name="moishe", id=100)
auth = Auth(props="abc")

state = {}


class AuthMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, request: HTTPConnection) -> AuthenticationResult:
        param = request.headers.get("Authorization")
        if param in state:
            return state.pop(param)
        raise PermissionDeniedException("unauthenticated")


@get(path="/")
def http_route_handler(request: Request[User, Auth]) -> None:
    assert isinstance(request.user, User)
    assert isinstance(request.auth, Auth)
    return None


def test_authentication_middleware_http_routes():
    client = create_test_client(route_handlers=[http_route_handler], middleware=[AuthMiddleware])
    token = "abc"
    error_response = client.get("/", headers={"Authorization": token})
    assert error_response.status_code == HTTP_403_FORBIDDEN
    state[token] = AuthenticationResult(user=user, auth=auth)
    success_response = client.get("/", headers={"Authorization": token})
    assert success_response.status_code == HTTP_200_OK


def test_authentication_middleware_not_installed_raises_for_user_scope_http():
    @get(path="/")
    def http_route_handler_user_scope(request: Request[User, None]) -> None:
        assert request.user

    client = create_test_client(route_handlers=[http_route_handler_user_scope])
    error_response = client.get("/", headers={"Authorization": "nope"})
    assert error_response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert error_response.json()["detail"] == "'user' is not defined in scope, install an AuthMiddleware to set it"


def test_authentication_middleware_not_installed_raises_for_auth_scope_http():
    @get(path="/")
    def http_route_handler_auth_scope(request: Request[None, Auth]) -> None:
        assert request.auth

    client = create_test_client(route_handlers=[http_route_handler_auth_scope])
    error_response = client.get("/", headers={"Authorization": "nope"})
    assert error_response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert error_response.json()["detail"] == "'auth' is not defined in scope, install an AuthMiddleware to set it"


@websocket(path="/")
async def websocket_route_handler(socket: WebSocket[User, Auth]) -> None:
    await socket.accept()
    assert isinstance(socket.user, User)
    assert isinstance(socket.auth, Auth)
    assert isinstance(socket.app, Starlite)
    await socket.send_json({"data": "123"})
    await socket.close()


def test_authentication_middleware_websocket_routes():
    token = "abc"
    client = create_test_client(route_handlers=websocket_route_handler, middleware=[AuthMiddleware])
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/", headers={"Authorization": token}) as ws:
        assert ws.receive_json()
    state[token] = AuthenticationResult(user=user, auth=auth)
    with client.websocket_connect("/", headers={"Authorization": token}) as ws:
        assert ws.receive_json()


def test_authentication_middleware_not_installed_raises_for_user_scope_websocket():
    @websocket(path="/")
    async def route_handler(socket: WebSocket[User, Auth]) -> None:
        await socket.accept()
        assert isinstance(socket.user, User)

    client = create_test_client(route_handlers=route_handler)
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/", headers={"Authorization": "yep"}) as ws:
        ws.receive_json()


def test_authentication_middleware_not_installed_raises_for_auth_scope_websocket():
    @websocket(path="/")
    async def route_handler(socket: WebSocket[User, Auth]) -> None:
        await socket.accept()
        assert isinstance(socket.auth, Auth)

    client = create_test_client(route_handlers=route_handler)
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/", headers={"Authorization": "yep"}) as ws:
        ws.receive_json()
