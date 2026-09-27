"""Tests for the Climate Entity Builder companion binary sensors."""

from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.climate_entity_builder.const import DOMAIN

from .helpers import HEATER, TEMP_SENSOR, async_setup_base, make_hub_entry, thermostat_subentry

CLIMATE_ENTITY_ID = "climate.schlafzimmer"


async def _setup(hass, **overrides):
    entry = make_hub_entry(subentries=[thermostat_subentry(**overrides)])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _binary_sensor_entity_id(hass, entry, suffix: str) -> str:
    subentry_id = next(iter(entry.subentries))
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{subentry_id}_{suffix}")
    assert entity_id is not None
    return entity_id


async def test_heating_activity_mirrors_heater_state(hass) -> None:
    """The heating-activity sensor tracks the real heater output, not the mode."""
    await async_setup_base(hass, temperature=19.0)
    entry = await _setup(hass)
    entity_id = _binary_sensor_entity_id(hass, entry, "heating_activity")

    assert hass.states.get(entity_id).state == "off"

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": CLIMATE_ENTITY_ID, "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": CLIMATE_ENTITY_ID, "temperature": 21.0},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(HEATER).state == "on"
    assert hass.states.get(entity_id).state == "on"


async def test_failsafe_binary_sensor_mirrors_climate_failsafe(hass) -> None:
    """The failsafe sensor turns on/off in step with the climate entity's failsafe."""
    await async_setup_base(hass, temperature=19.0)
    entry = await _setup(hass)
    entity_id = _binary_sensor_entity_id(hass, entry, "failsafe")

    assert hass.states.get(entity_id).state == "off"

    hass.states.async_set(TEMP_SENSOR, "unavailable")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=16))
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "on"

    hass.states.async_set(TEMP_SENSOR, "19.0")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "off"
