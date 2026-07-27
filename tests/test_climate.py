"""Tests for the climate entity state mapping and command emission."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

from custom_components.ewpe_smart.climate import (
    FAN_MEDIUM_HIGH,
    FAN_MEDIUM_LOW,
    FAN_QUIET,
    FAN_TURBO,
    EwpeClimateEntity,
)
from custom_components.ewpe_smart.const import (
    PARAM_FAN_SPEED,
    PARAM_MODE,
    PARAM_POWER,
    PARAM_QUIET,
    PARAM_SET_TEMP,
    PARAM_TURBO,
)


def _make_entity(status: dict[str, int]) -> tuple[EwpeClimateEntity, MagicMock]:
    coordinator = MagicMock()
    coordinator.data = status
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

    entity = EwpeClimateEntity(coordinator, entry)
    return entity, device


def test_power_off_maps_to_hvac_off() -> None:
    entity, _ = _make_entity({"Pow": 0, "Mod": 1})
    assert entity.hvac_mode == HVACMode.OFF


def test_climate_uses_translation_key_for_custom_fan_modes() -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1})
    assert entity.translation_key == "air_conditioner"


@pytest.mark.parametrize(
    ("device_mode", "expected"),
    [
        (0, HVACMode.AUTO),
        (1, HVACMode.COOL),
        (2, HVACMode.DRY),
        (3, HVACMode.FAN_ONLY),
        (4, HVACMode.HEAT),
    ],
)
def test_modes_map_correctly(device_mode: int, expected: HVACMode) -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": device_mode})
    assert entity.hvac_mode == expected


@pytest.mark.parametrize(
    ("speed", "expected"),
    [
        (0, FAN_AUTO),
        (1, FAN_LOW),
        (2, FAN_MEDIUM_LOW),
        (3, FAN_MEDIUM),
        (4, FAN_MEDIUM_HIGH),
        (5, FAN_HIGH),
    ],
)
def test_fan_modes_map_correctly(speed: int, expected: str) -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "WdSpd": speed})
    assert entity.fan_mode == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"WdSpd": 1, "Quiet": 2, "Tur": 0}, FAN_QUIET),
        ({"WdSpd": 0, "Quiet": 0, "Tur": 1}, FAN_TURBO),
    ],
)
def test_special_fan_modes_override_speed(
    status: dict[str, int], expected: str
) -> None:
    entity, _ = _make_entity(status)
    assert entity.fan_mode == expected


def test_target_and_current_temperature() -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "SetTem": 23, "TemSen": 25})
    assert entity.target_temperature == 23.0
    assert entity.current_temperature == 25.0


def test_implausible_temp_sensor_is_none() -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "TemSen": -50})
    assert entity.current_temperature is None


@pytest.mark.asyncio
async def test_set_temperature_emits_set_tem() -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1, "SetTem": 22})
    await entity.async_set_temperature(temperature=24)
    device.set_state.assert_awaited_once_with({PARAM_SET_TEMP: 24})


@pytest.mark.asyncio
async def test_set_hvac_mode_off_emits_pow_zero() -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1})
    await entity.async_set_hvac_mode(HVACMode.OFF)
    device.set_state.assert_awaited_once_with({PARAM_POWER: 0})


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_emits_pow_on_and_mode_heat() -> None:
    entity, device = _make_entity({"Pow": 0})
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    device.set_state.assert_awaited_once_with({PARAM_POWER: 1, PARAM_MODE: 4})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fan_mode", "speed", "quiet", "turbo"),
    [
        (FAN_AUTO, 0, 0, 0),
        (FAN_QUIET, 1, 2, 0),
        (FAN_TURBO, 0, 0, 1),
        (FAN_LOW, 1, 0, 0),
        (FAN_MEDIUM_LOW, 2, 0, 0),
        (FAN_MEDIUM, 3, 0, 0),
        (FAN_MEDIUM_HIGH, 4, 0, 0),
        (FAN_HIGH, 5, 0, 0),
    ],
)
async def test_set_fan_mode_emits_complete_state(
    fan_mode: str, speed: int, quiet: int, turbo: int
) -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1})
    await entity.async_set_fan_mode(fan_mode)
    device.set_state.assert_awaited_once_with(
        {PARAM_FAN_SPEED: speed, PARAM_QUIET: quiet, PARAM_TURBO: turbo}
    )


@pytest.mark.asyncio
async def test_turn_on_off_shortcuts() -> None:
    entity, device = _make_entity({"Pow": 0})
    await entity.async_turn_on()
    device.set_state.assert_awaited_with({PARAM_POWER: 1})
    await entity.async_turn_off()
    device.set_state.assert_awaited_with({PARAM_POWER: 0})
