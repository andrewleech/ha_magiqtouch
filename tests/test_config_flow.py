"""Tests for MagIQtouch config-flow error classification."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.magiqtouch import config_flow


def make_driver(*, login_result=True, login_error=None):
    driver = Mock()
    if login_error is not None:
        driver.login = AsyncMock(side_effect=login_error)
    else:
        driver.login = AsyncMock(return_value=login_result)
    driver.startup = AsyncMock()
    driver.update_config_data = Mock(return_value={"title": "Synthetic MagIQtouch"})
    return driver


@pytest.mark.asyncio
async def test_validate_input_preserves_invalid_auth(monkeypatch) -> None:
    driver = make_driver(login_result=False)
    monkeypatch.setattr(config_flow, "MagIQtouch_Driver", Mock(return_value=driver))

    with pytest.raises(config_flow.InvalidAuth):
        await config_flow.validate_input(
            object(),
            {"username": "test@example.invalid", "password": "not-a-real-password"},
        )


@pytest.mark.asyncio
async def test_validate_input_classifies_invalid_signature(monkeypatch) -> None:
    error = RuntimeError("InvalidSignatureException: synthetic clock skew")
    driver = make_driver(login_error=error)
    monkeypatch.setattr(config_flow, "MagIQtouch_Driver", Mock(return_value=driver))

    with pytest.raises(config_flow.InvalidTime) as raised:
        await config_flow.validate_input(
            object(),
            {"username": "test@example.invalid", "password": "not-a-real-password"},
        )

    assert raised.value.__cause__ is error


@pytest.mark.asyncio
async def test_validate_input_classifies_connection_error(monkeypatch) -> None:
    error = ConnectionError("synthetic connection failure")
    driver = make_driver(login_error=error)
    monkeypatch.setattr(config_flow, "MagIQtouch_Driver", Mock(return_value=driver))

    with pytest.raises(config_flow.CannotConnect) as raised:
        await config_flow.validate_input(
            object(),
            {"username": "test@example.invalid", "password": "not-a-real-password"},
        )

    assert raised.value.__cause__ is error
