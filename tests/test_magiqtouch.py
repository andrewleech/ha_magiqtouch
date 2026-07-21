"""Tests for the MagIQtouch cloud driver's WebSocket lifecycle."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from custom_components.magiqtouch.magiqtouch import MagIQtouch_Driver, WebsocketJob


class FakeWebSocket:
    """Minimal aiohttp WebSocket context manager with scripted receive results."""

    def __init__(self, *results) -> None:
        self._results = list(results)
        self.closed = False
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.closed = True

    async def send_str(self, message: str) -> None:
        self.sent.append(message)

    async def receive(self):
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def close(self) -> None:
        self.closed = True


class FakeSession:
    """Capture ws_connect parameters and return a scripted WebSocket."""

    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.connect_kwargs = None

    def ws_connect(self, *args, **kwargs):
        self.connect_kwargs = kwargs
        return self.websocket

    @property
    def receive_timeout(self):
        timeout = self.connect_kwargs["timeout"]
        if hasattr(timeout, "ws_receive"):
            return timeout.ws_receive
        return self.connect_kwargs["receive_timeout"]


@pytest.fixture
def driver() -> MagIQtouch_Driver:
    test_driver = MagIQtouch_Driver("test@example.invalid", "not-a-real-password")
    test_driver._refresh_msg = "refresh"
    return test_driver


def text_message(data: dict) -> SimpleNamespace:
    return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(data))


@pytest.mark.asyncio
async def test_ws_send_stores_timeout_as_duration(driver, monkeypatch) -> None:
    captured_job = None

    async def timeout_handler(job):
        nonlocal captured_job
        captured_job = job
        raise asyncio.TimeoutError

    monkeypatch.setattr(driver, "ws_handler", timeout_handler)

    assert await driver.ws_send("{}", lambda state: True, timeout=8) is False
    assert captured_job.timeout == 8


@pytest.mark.asyncio
async def test_idle_receive_timeout_returns_false_and_cleans_up(driver, monkeypatch) -> None:
    websocket = FakeWebSocket(asyncio.TimeoutError())
    session = FakeSession(websocket)
    driver._httpsession = session
    monkeypatch.setattr(driver, "_get_token", AsyncMock(return_value="token"))

    result = await driver.ws_send("{}", lambda state: True, timeout=8)

    assert result is False
    assert session.receive_timeout == 8
    assert driver.jobs == []


@pytest.mark.asyncio
async def test_background_response_then_timeout_is_success(driver, monkeypatch) -> None:
    websocket = FakeWebSocket(
        text_message(
            {
                "device": "synthetic-device",
                "timestamp": 2,
                "runningMode": "COOL",
            }
        ),
        asyncio.TimeoutError(),
    )
    session = FakeSession(websocket)
    driver._httpsession = session
    monkeypatch.setattr(driver, "_get_token", AsyncMock(return_value="token"))

    result = await driver.ws_send("{}", checker=None, timeout=8)

    assert result is True
    assert driver.current_state.device == "synthetic-device"
    assert driver.jobs == []


@pytest.mark.asyncio
async def test_closed_socket_without_confirmation_returns_false(driver, monkeypatch) -> None:
    websocket = FakeWebSocket(None)
    session = FakeSession(websocket)
    driver._httpsession = session
    monkeypatch.setattr(driver, "_get_token", AsyncMock(return_value="token"))

    result = await driver.ws_send("{}", lambda state: True, timeout=8)

    assert result is False
    assert driver.jobs == []


@pytest.mark.asyncio
async def test_matching_response_returns_true(driver, monkeypatch) -> None:
    websocket = FakeWebSocket(
        text_message(
            {
                "device": "synthetic-device",
                "timestamp": 2,
                "runningMode": "COOL",
            }
        )
    )
    session = FakeSession(websocket)
    driver._httpsession = session
    monkeypatch.setattr(driver, "_get_token", AsyncMock(return_value="token"))
    monkeypatch.setattr(driver, "background_refresh", AsyncMock())

    result = await driver.ws_send(
        "command",
        lambda state: state.device == "synthetic-device",
        timeout=8,
    )

    assert result is True
    assert driver.jobs == []


@pytest.mark.asyncio
async def test_unexpected_websocket_error_propagates_and_cleans_up(driver, monkeypatch) -> None:
    websocket = FakeWebSocket(RuntimeError("synthetic network failure"))
    session = FakeSession(websocket)
    driver._httpsession = session
    monkeypatch.setattr(driver, "_get_token", AsyncMock(return_value="token"))
    job = WebsocketJob("{}", lambda state: True, status=0, timeout=8)

    with pytest.raises(RuntimeError, match="synthetic network failure"):
        await driver.ws_handler(job)

    assert driver.jobs == []
