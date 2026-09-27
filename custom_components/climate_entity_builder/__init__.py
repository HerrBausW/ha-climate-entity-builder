"""The Climate Entity Builder integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DATA_FAILSAFE_STATES, DOMAIN

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.BINARY_SENSOR]

type RoomThermostatConfigEntry = ConfigEntry[None]


async def async_setup_entry(hass: HomeAssistant, entry: RoomThermostatConfigEntry) -> bool:
    """Set up Climate Entity Builder from a config entry."""
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_FAILSAFE_STATES, {})
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoomThermostatConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: RoomThermostatConfigEntry) -> None:
    """Reload the hub whenever a thermostat subentry is added, edited or removed."""
    await hass.config_entries.async_reload(entry.entry_id)
