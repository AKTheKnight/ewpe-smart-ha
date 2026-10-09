"""Polling coordinator for an EWPE Smart device."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device import EwpeAuthError, EwpeDevice, EwpeError, EwpeTimeout

_LOGGER = logging.getLogger(__name__)
_STATUS_RETRY_DELAYS = (0.25, 0.5)


class EwpeCoordinator(DataUpdateCoordinator[dict[str, int]]):
    """Polls a single EwpeDevice and surfaces failures to HA."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: EwpeDevice,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {device.name or device.host}",
            update_interval=timedelta(seconds=update_interval),
            config_entry=entry,
        )
        self.device = device

    async def _async_update_data(self) -> dict[str, int]:
        try:
            for attempt in range(len(_STATUS_RETRY_DELAYS) + 1):
                try:
                    return await self.device.get_status()
                except EwpeTimeout:
                    if attempt == len(_STATUS_RETRY_DELAYS):
                        raise
                    delay = _STATUS_RETRY_DELAYS[attempt]
                    _LOGGER.debug(
                        "Status request to %s timed out; retrying in %.2fs",
                        self.device.host,
                        delay,
                    )
                    await asyncio.sleep(delay)
        except EwpeAuthError as err:
            raise ConfigEntryAuthFailed(
                "Device key rejected; reauthentication required"
            ) from err
        except EwpeError as err:
            raise UpdateFailed(str(err)) from err
