"""Tests for the MagIQtouch cloud driver's WebSocket lifecycle."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import aiohttp
import pytest

from custom_components.magiqtouch.const import (
    CONTROL_MODE_FAN,
    CONTROL_MODE_TEMP,
    MODE_COOLER,
    MODE_COOLER_FAN,
    MODE_HEATER,
    ZONE_COMMON,
    ZoneType,
)
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
    test_driver._state_confirmed = True
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


@pytest.mark.asyncio
async def test_full_refresh_raises_when_no_state_is_received(driver) -> None:
    driver.logged_in = True
    driver.ws_send = AsyncMock(return_value=False)

    with pytest.raises(asyncio.TimeoutError):
        await driver.full_refresh()


@pytest.mark.asyncio
async def test_failed_pre_command_refresh_prevents_stale_command(driver) -> None:
    driver._state_confirmed = False
    driver.ws_send = AsyncMock(return_value=False)

    with pytest.raises(asyncio.TimeoutError):
        await driver.send_current_state(lambda state: True)

    driver.ws_send.assert_awaited_once_with(
        driver._refresh_msg,
        ANY,
        timeout=5,
    )


@pytest.mark.asyncio
async def test_pre_command_refresh_preserves_requested_payload(
    driver, make_unit, make_remote_status
) -> None:
    driver._state_confirmed = False
    driver.current_state = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=1)]
    )
    refreshed_state = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=1)]
    )
    sent_commands = []

    async def ws_send(message, checker, timeout=8):
        if message == driver._refresh_msg:
            driver.process_new_state(refreshed_state)
        else:
            sent_commands.append(json.loads(message))
        return True

    driver.ws_send = AsyncMock(side_effect=ws_send)

    await driver.set_cooling_by_speed(ZONE_COMMON, 8)

    assert sent_commands[0]["params"]["cooler"][0]["control_mode"] == CONTROL_MODE_FAN
    assert sent_commands[0]["params"]["cooler"][0]["fan_speed"] == 8


def test_state_checker_rejects_missing_zone(driver, make_unit, make_remote_status) -> None:
    state = make_remote_status(cooler=[make_unit()])
    missing_zone = ZoneType("INDIVIDUAL", "Bedroom")

    assert (
        driver.state_checker(
            state,
            units="c",
            zone=missing_zone,
            field="fan_speed",
            value=5,
        )
        is False
    )


def test_state_checker_rejects_missing_equipment(driver, make_remote_status) -> None:
    state = make_remote_status(cooler=[])

    assert (
        driver.state_checker(
            state,
            units="c",
            zone=ZONE_COMMON,
            field="fan_speed",
            value=5,
        )
        is False
    )


def test_state_checker_does_not_mutate_response_equipment_lists(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit()
    heater = make_unit()
    state = make_remote_status(cooler=[cooler], heater=[heater])

    assert driver.state_checker(
        state,
        units="hc",
        zone=ZONE_COMMON,
        field="fan_speed",
        value=5,
    )
    assert state.cooler == [cooler]
    assert state.heater == [heater]


def test_process_new_state_invalidates_detached_equipment_cache(
    driver, make_unit, make_remote_status
) -> None:
    driver.current_state = make_remote_status(cooler=[make_unit(name="Cached")])
    cached_unit = driver.available_coolers(ZONE_COMMON)[0]
    refreshed_unit = make_unit(name="Controller")

    driver.process_new_state(make_remote_status(cooler=[refreshed_unit]))

    assert driver.available_coolers(ZONE_COMMON) == [driver.current_state.cooler[0]]
    assert driver.available_coolers(ZONE_COMMON)[0] is not cached_unit


@pytest.mark.asyncio
async def test_generic_fan_only_refreshes_before_selecting_equipment(
    driver, make_unit, make_remote_status
) -> None:
    driver.current_state = make_remote_status(
        cooler=[make_unit()],
        heater=[make_unit(name="Heater")],
        running_mode=MODE_COOLER,
    )
    live_state = make_remote_status(
        cooler=[make_unit()],
        heater=[make_unit(name="Heater")],
        running_mode=MODE_HEATER,
    )

    async def ensure_state_confirmed():
        driver.process_new_state(live_state)

    driver.ensure_state_confirmed = AsyncMock(side_effect=ensure_state_confirmed)
    driver.set_fan_only_evap = AsyncMock()
    driver.set_fan_only_heater = AsyncMock()

    await driver.set_fan_only(ZONE_COMMON)

    driver.set_fan_only_heater.assert_awaited_once_with(ZONE_COMMON)
    driver.set_fan_only_evap.assert_not_awaited()


def test_command_timestamp_uses_remote_millisecond_precision(driver) -> None:
    driver.current_state.timestamp = 1_784_871_517_437

    command = driver.new_remote_props()

    assert command["params"]["timestamp"] >= 1_000_000_000_000


@pytest.mark.asyncio
async def test_background_refresh_contains_task_failure(driver, caplog) -> None:
    tasks = []
    driver.full_refresh = AsyncMock(side_effect=RuntimeError("synthetic refresh failure"))
    driver.create_task = Mock(
        side_effect=lambda coroutine: tasks.append(asyncio.create_task(coroutine))
    )

    with caplog.at_level("WARNING", logger="magiqtouch"):
        await driver.background_refresh()
        await tasks[0]

    assert "background refresh failed" in caplog.text.lower()


@pytest.mark.asyncio
async def test_temperature_command_atomically_selects_cooling_and_setpoint(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_FAN, set_temp=22.0)
    driver.current_state = make_remote_status(
        cooler=[cooler],
        running_mode=MODE_COOLER_FAN,
    )
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_temperature(ZONE_COMMON, 26)

    assert driver.current_state.systemOn is True
    assert driver.current_state.runningMode == MODE_COOLER
    assert cooler.control_mode == CONTROL_MODE_TEMP
    assert cooler.set_temp == 26
    driver.send_current_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_speed_command_atomically_selects_cooling_and_speed(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=3)
    driver.current_state = make_remote_status(cooler=[cooler])
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_speed(ZONE_COMMON, 8)

    assert driver.current_state.runningMode == MODE_COOLER
    assert cooler.control_mode == CONTROL_MODE_FAN
    assert cooler.fan_speed == 8
    assert driver.current_state.fan.cooler_Fan_Speed == 8
    driver.send_current_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_speed_command_requires_controller_to_confirm_nested_speed(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=3)
    driver.current_state = make_remote_status(cooler=[cooler])
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_speed(ZONE_COMMON, 8)

    checker = driver.send_current_state.await_args.args[0]
    unconfirmed = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_FAN, fan_speed=3)]
    )
    wrong_control_mode = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=8)]
    )
    wrong_global_speed = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_FAN, fan_speed=8)]
    )
    wrong_global_speed.fan.cooler_Fan_Speed = 1
    confirmed = make_remote_status(cooler=[make_unit(control_mode=CONTROL_MODE_FAN, fan_speed=8)])
    confirmed.fan.cooler_Fan_Speed = 8
    assert checker(unconfirmed) is False
    assert checker(wrong_control_mode) is False
    assert checker(wrong_global_speed) is False
    assert checker(confirmed) is True


@pytest.mark.asyncio
async def test_temperature_command_requires_controller_to_confirm_nested_setpoint(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_FAN, set_temp=22.0)
    driver.current_state = make_remote_status(cooler=[cooler])
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_temperature(ZONE_COMMON, 26)

    checker = driver.send_current_state.await_args.args[0]
    unconfirmed = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_TEMP, set_temp=22.0)]
    )
    wrong_control_mode = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_FAN, set_temp=26.0)]
    )
    confirmed = make_remote_status(
        cooler=[make_unit(control_mode=CONTROL_MODE_TEMP, set_temp=26.0)]
    )
    assert checker(unconfirmed) is False
    assert checker(wrong_control_mode) is False
    assert checker(confirmed) is True


@pytest.mark.asyncio
async def test_fresh_air_command_requires_controller_to_confirm_returned_mode(
    driver, make_unit, make_remote_status
) -> None:
    driver.current_state = make_remote_status(
        cooler=[make_unit()],
        running_mode=MODE_COOLER,
    )
    driver.send_current_state = AsyncMock()

    await driver.set_fan_only_evap(ZONE_COMMON)

    checker = driver.send_current_state.await_args.args[0]
    wrong_mode = make_remote_status(
        cooler=[make_unit()],
        running_mode=MODE_COOLER,
    )
    confirmed = make_remote_status(
        cooler=[make_unit()],
        running_mode=MODE_COOLER_FAN,
    )
    assert checker(wrong_mode) is False
    assert checker(confirmed) is True


@pytest.mark.asyncio
async def test_air_only_speed_change_only_updates_active_cooler(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(fan_speed=3)
    heater = make_unit(name="Heater", fan_speed=4)
    driver.current_state = make_remote_status(
        cooler=[cooler],
        heater=[heater],
        running_mode=MODE_COOLER_FAN,
    )
    driver.send_current_state = AsyncMock()

    await driver.set_current_speed(7, ZONE_COMMON)

    assert driver.current_state.runningMode == MODE_COOLER_FAN
    assert cooler.fan_speed == 7
    assert driver.current_state.fan.cooler_Fan_Speed == 7
    assert heater.fan_speed == 4
    driver.send_current_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_heater_speed_updates_and_confirms_global_fan_speed(
    driver, make_unit, make_remote_status
) -> None:
    heater = make_unit(name="Heater", control_mode=CONTROL_MODE_TEMP, fan_speed=3)
    driver.current_state = make_remote_status(
        heater=[heater],
        running_mode=MODE_HEATER,
    )
    driver.send_current_state = AsyncMock()

    await driver.set_heating_by_speed(ZONE_COMMON, 6)

    checker = driver.send_current_state.await_args.args[0]
    wrong_global_speed = make_remote_status(
        heater=[make_unit(name="Heater", control_mode=CONTROL_MODE_FAN, fan_speed=6)],
        running_mode=MODE_HEATER,
    )
    wrong_global_speed.fan.heater_Fan_Speed = 1
    confirmed = make_remote_status(
        heater=[make_unit(name="Heater", control_mode=CONTROL_MODE_FAN, fan_speed=6)],
        running_mode=MODE_HEATER,
    )
    confirmed.fan.heater_Fan_Speed = 6

    assert heater.fan_speed == 6
    assert driver.current_state.fan.heater_Fan_Speed == 6
    assert checker(wrong_global_speed) is False
    assert checker(confirmed) is True
