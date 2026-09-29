"""Diagnostics support for Climate Entity Builder."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SUBENTRY_TYPE_PROFILE, SUBENTRY_TYPE_THERMOSTAT


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    No credentials or external identifiers exist in this integration; the
    entity ids referenced here are the user's own local Home Assistant
    entities, exposed the same way they already are in the entity registry.
    """
    registry = er.async_get(hass)

    thermostats: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_TYPE_PROFILE:
            profiles.append({"title": subentry.title, "configuration": dict(subentry.data)})
            continue
        if subentry.subentry_type != SUBENTRY_TYPE_THERMOSTAT:
            continue
        entity_id = registry.async_get_entity_id("climate", DOMAIN, subentry.subentry_id)
        state = hass.states.get(entity_id) if entity_id else None
        thermostats.append(
            {
                "title": subentry.title,
                "configuration": dict(subentry.data),
                "entity_id": entity_id,
                "state": state.state if state else None,
                "attributes": dict(state.attributes) if state else None,
            }
        )

    return {"entry_title": entry.title, "thermostats": thermostats, "profiles": profiles}
