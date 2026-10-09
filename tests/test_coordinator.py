"""Tests for the EWPE Smart polling coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ewpe_smart.coordinator import EwpeCoordinator
from custom_components.ewpe_smart.device import (
    EwpeAuthError,
    EwpeDevice,
    EwpeProtocolError,
    EwpeTimeout,
)


def coordinator_with(device: EwpeDevice) -> EwpeCoordinator:
    """Create a coordinator without initializing Home Assistant machinery."""
    coordinator = object.__new__(EwpeCoordinator)
    coordinator.device = device
    return coordinator


@pytest.mark.asyncio
async def test_status_succeeds_without_retry() -> None:
    """A successful poll returns immediately."""
    device = EwpeDevice("192.0.2.1")
    device.get_status = AsyncMock(return_value={"Pow": 1})

    with patch(
        "custom_components.ewpe_smart.coordinator.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep:
        result = await coordinator_with(device)._async_update_data()

    assert result == {"Pow": 1}
    device.get_status.assert_awaited_once_with()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_retries_twice_after_timeouts() -> None:
    """Timeouts are retried after 250 ms and 500 ms."""
    device = EwpeDevice("192.0.2.1")
    device.get_status = AsyncMock(
        side_effect=[
            EwpeTimeout("first timeout"),
            EwpeTimeout("second timeout"),
            {"Pow": 1},
        ]
    )

    with patch(
        "custom_components.ewpe_smart.coordinator.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep:
        result = await coordinator_with(device)._async_update_data()

    assert result == {"Pow": 1}
    assert device.get_status.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [0.25, 0.5]


@pytest.mark.asyncio
async def test_status_fails_after_three_timeouts() -> None:
    """Three consecutive timeouts make the coordinator update fail."""
    device = EwpeDevice("192.0.2.1")
    device.get_status = AsyncMock(side_effect=EwpeTimeout("still unreachable"))

    with (
        patch(
            "custom_components.ewpe_smart.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep,
        pytest.raises(UpdateFailed, match="still unreachable"),
    ):
        await coordinator_with(device)._async_update_data()

    assert device.get_status.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [0.25, 0.5]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (EwpeAuthError("bad key"), ConfigEntryAuthFailed),
        (EwpeProtocolError("bad reply"), UpdateFailed),
    ],
)
async def test_non_timeout_errors_are_not_retried(
    error: Exception, expected: type[Exception]
) -> None:
    """Authentication and protocol errors fail without retrying."""
    device = EwpeDevice("192.0.2.1")
    device.get_status = AsyncMock(side_effect=error)

    with (
        patch(
            "custom_components.ewpe_smart.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep,
        pytest.raises(expected),
    ):
        await coordinator_with(device)._async_update_data()

    device.get_status.assert_awaited_once_with()
    sleep.assert_not_awaited()
