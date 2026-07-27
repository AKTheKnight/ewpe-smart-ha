"""Optional feature switches for EWPE Smart devices."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    PARAM_DISPLAY_LIGHT,
    PARAM_ENERGY_SAVING,
    PARAM_FRESH_AIR,
    PARAM_HEALTH,
    PARAM_SLEEP,
    PARAM_SLEEP_MODE,
    PARAM_XFAN,
)
from .coordinator import EwpeCoordinator

SWITCH_DESCRIPTIONS = (
    SwitchEntityDescription(key=PARAM_SLEEP, translation_key="sleep"),
    SwitchEntityDescription(key=PARAM_XFAN, translation_key="xfan"),
    SwitchEntityDescription(key=PARAM_HEALTH, translation_key="health"),
    SwitchEntityDescription(key=PARAM_DISPLAY_LIGHT, translation_key="display_light"),
    SwitchEntityDescription(key=PARAM_ENERGY_SAVING, translation_key="energy_saving"),
    SwitchEntityDescription(
        key=PARAM_FRESH_AIR,
        translation_key="fresh_air",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EwpeCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    async_add_entities(
        EwpeFeatureSwitch(coordinator, entry, description)
        for description in SWITCH_DESCRIPTIONS
        if description.key in data
    )


class EwpeFeatureSwitch(CoordinatorEntity[EwpeCoordinator], SwitchEntity):
    """Controls one optional feature exposed by an EWPE Smart device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        entry: ConfigEntry,
        description: SwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self.entity_description = description
        self._attr_unique_id = f"{device.mac}_{description.translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.mac or entry.entry_id)},
            name=device.name or entry.title,
            manufacturer=MANUFACTURER,
            model=device.info.get("model") if device.info else None,
            sw_version=device.info.get("ver") if device.info else None,
        )

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get(self.entity_description.key))

    async def async_turn_on(self, **kwargs: object) -> None:
        key = self.entity_description.key
        if key == PARAM_SLEEP:
            values = {PARAM_SLEEP: 1, PARAM_SLEEP_MODE: 1}
        else:
            values = {key: 1}
        await self.coordinator.device.set_state(values)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: object) -> None:
        key = self.entity_description.key
        values = (
            {PARAM_SLEEP: 0, PARAM_SLEEP_MODE: 0} if key == PARAM_SLEEP else {key: 0}
        )
        await self.coordinator.device.set_state(values)
        await self.coordinator.async_request_refresh()
