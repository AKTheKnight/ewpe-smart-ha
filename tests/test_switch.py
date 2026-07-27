"""Tests for optional feature switches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ewpe_smart.const import (
    DOMAIN,
    PARAM_FRESH_AIR,
    PARAM_HEALTH,
    PARAM_SLEEP,
    PARAM_SLEEP_MODE,
    PARAM_XFAN,
)
from custom_components.ewpe_smart.switch import (
    SWITCH_DESCRIPTIONS,
    EwpeFeatureSwitch,
    async_setup_entry,
)


def _make_entity(key: str, value: int = 0) -> tuple[EwpeFeatureSwitch, MagicMock]:
    coordinator = MagicMock()
    coordinator.data = {key: value}
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    device = MagicMock()
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Test"
    device.info = {}
    device.set_state = AsyncMock()
    coordinator.device = device

    entry = MagicMock()
    entry.entry_id = "abc"
    entry.title = "Test"
    description = next(item for item in SWITCH_DESCRIPTIONS if item.key == key)
    return EwpeFeatureSwitch(coordinator, entry, description), device


@pytest.mark.parametrize(("value", "expected"), [(0, False), (1, True), (2, True)])
def test_state_mapping(value: int, expected: bool) -> None:
    entity, _ = _make_entity(PARAM_XFAN, value)
    assert entity.is_on is expected


@pytest.mark.asyncio
async def test_standard_switch_commands_and_refreshes() -> None:
    entity, device = _make_entity(PARAM_XFAN)

    await entity.async_turn_on()
    device.set_state.assert_awaited_once_with({PARAM_XFAN: 1})
    entity.coordinator.async_request_refresh.assert_awaited_once()

    device.set_state.reset_mock()
    entity.coordinator.async_request_refresh.reset_mock()
    await entity.async_turn_off()
    device.set_state.assert_awaited_once_with({PARAM_XFAN: 0})
    entity.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_sleep_commands_both_properties() -> None:
    entity, device = _make_entity(PARAM_SLEEP)

    await entity.async_turn_on()
    device.set_state.assert_awaited_once_with({PARAM_SLEEP: 1, PARAM_SLEEP_MODE: 1})

    device.set_state.reset_mock()
    await entity.async_turn_off()
    device.set_state.assert_awaited_once_with({PARAM_SLEEP: 0, PARAM_SLEEP_MODE: 0})


def test_fresh_air_is_disabled_by_default() -> None:
    description = next(
        item for item in SWITCH_DESCRIPTIONS if item.key == PARAM_FRESH_AIR
    )
    assert description.entity_registry_enabled_default is False


@pytest.mark.asyncio
async def test_setup_only_adds_properties_returned_by_device() -> None:
    coordinator = MagicMock()
    coordinator.data = {PARAM_XFAN: 0, PARAM_HEALTH: 1}
    hass = MagicMock()
    hass.data = {DOMAIN: {"abc": coordinator}}
    entry = MagicMock()
    entry.entry_id = "abc"
    added: list[EwpeFeatureSwitch] = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert [entity.entity_description.key for entity in added] == [
        PARAM_XFAN,
        PARAM_HEALTH,
    ]
