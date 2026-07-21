"""Tests for awaited coordinator refresh and retry behaviour."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.magiqtouch import MagIQtouchCoordinator
from custom_components.magiqtouch.magiqtouch import MagIQtouch_Driver


@pytest.mark.asyncio
async def test_driver_refresh_state_awaits_full_refresh() -> None:
    driver = MagIQtouch_Driver("test@example.invalid", "not-a-real-password")
    driver.full_refresh = AsyncMock()
    driver.background_refresh = AsyncMock()

    await driver.refresh_state()

    driver.full_refresh.assert_awaited_once_with()
    driver.background_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_coordinator_retries_refresh_after_login() -> None:
    controller = SimpleNamespace(
        refresh_state=AsyncMock(
            side_effect=[RuntimeError("synthetic first failure"), "refreshed"]
        ),
        login=AsyncMock(return_value=True),
    )
    coordinator = object.__new__(MagIQtouchCoordinator)
    coordinator.controller = controller

    result = await coordinator._async_update_data()

    assert result == "refreshed"
    assert controller.refresh_state.await_count == 2
    controller.login.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_after_retry() -> None:
    retry_error = RuntimeError("synthetic retry failure")
    controller = SimpleNamespace(
        refresh_state=AsyncMock(
            side_effect=[RuntimeError("synthetic first failure"), retry_error]
        ),
        login=AsyncMock(return_value=True),
    )
    coordinator = object.__new__(MagIQtouchCoordinator)
    coordinator.controller = controller

    with pytest.raises(UpdateFailed) as raised:
        await coordinator._async_update_data()

    assert raised.value.__cause__ is retry_error
    assert controller.refresh_state.await_count == 2


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_when_login_fails() -> None:
    first_error = RuntimeError("synthetic first failure")
    controller = SimpleNamespace(
        refresh_state=AsyncMock(side_effect=first_error),
        login=AsyncMock(return_value=False),
    )
    coordinator = object.__new__(MagIQtouchCoordinator)
    coordinator.controller = controller

    with pytest.raises(UpdateFailed) as raised:
        await coordinator._async_update_data()

    assert raised.value.__cause__ is first_error
    assert controller.refresh_state.await_count == 1
