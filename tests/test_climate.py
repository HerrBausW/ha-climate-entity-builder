"""Tests for the Room Thermostat climate entity behaviour."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import State
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.room_thermostat.const import ATTR_FAILSAFE_ACTIVE

from .helpers import (
    HEATER,
    SCHEDULE,
    TEMP_SENSOR,
    async_setup_base,
    make_hub_entry,
    thermostat_subentry,
)

CLIMATE_ENTITY_ID = "climate.thermostat_schlafzimmer"


async def _setup(hass, **overrides):
    entry = make_hub_entry(subentries=[thermostat_subentry(**overrides)])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_hvac_mode(hass, hvac_mode: str) -> None:
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": CLIMATE_ENTITY_ID, "hvac_mode": hvac_mode},
        blocking=True,
    )


async def _set_temperature(hass, temperature: float) -> None:
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": CLIMATE_ENTITY_ID, "temperature": temperature},
        blocking=True,
    )


async def test_heat_mode_turns_heater_on_when_cold(hass) -> None:
    """Item 3: heat-mode control turns the heater on when below target."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)

    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()

    assert hass.states.get(HEATER).state == "on"
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING


async def test_hysteresis_deadband_does_not_toggle(hass) -> None:
    """Item 4: within [target-cold, target+hot] the switch is left alone."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 20.0)  # cold=0.2, hot=0.2 -> on<=19.8, off>=20.2
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(TEMP_SENSOR, "19.9")
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"  # unchanged, inside dead-band

    hass.states.async_set(TEMP_SENSOR, "20.2")
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"

    hass.states.async_set(TEMP_SENSOR, "19.9")
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"  # unchanged, inside dead-band


async def test_auto_mode_uses_comfort_when_schedule_on(hass) -> None:
    """Item 5."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    hass.states.async_set(SCHEDULE, "on")
    await _set_hvac_mode(hass, HVACMode.AUTO)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] == 21.0
    assert hass.states.get(HEATER).state == "on"


async def test_auto_mode_uses_eco_when_schedule_off(hass) -> None:
    """Item 6."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    hass.states.async_set(SCHEDULE, "off")
    await _set_hvac_mode(hass, HVACMode.AUTO)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] == 18.0
    assert hass.states.get(HEATER).state == "off"


async def test_current_humidity_reported(hass) -> None:
    """Item 7."""
    await async_setup_base(hass, temperature=19.0, humidity=55.0)
    await _setup(hass)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes["current_humidity"] == 55


async def test_temperature_sensor_unavailable_no_immediate_failsafe(hass) -> None:
    """Item 8: a bad reading alone must not immediately trip the failsafe."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(TEMP_SENSOR, "unavailable")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_FAILSAFE_ACTIVE] is False
    assert hass.states.get(HEATER).state == "on"  # left untouched during grace period


async def test_failsafe_engages_after_timeout(hass) -> None:
    """Item 9: after sensor_stale_timeout minutes, the heater is forced off."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(TEMP_SENSOR, "unavailable")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=16))
    await hass.async_block_till_done()

    assert hass.states.get(HEATER).state == "off"
    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_FAILSAFE_ACTIVE] is True
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


async def test_sensor_recovery_resumes_normal_control(hass) -> None:
    """Item 10: once the sensor is valid again, control resumes automatically."""
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()

    hass.states.async_set(TEMP_SENSOR, "unavailable")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=16))
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"

    hass.states.async_set(TEMP_SENSOR, "19.0")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_FAILSAFE_ACTIVE] is False
    assert hass.states.get(HEATER).state == "on"


async def test_restart_restores_hvac_mode_and_temperature(hass) -> None:
    """Item 11: HVAC mode and manual setpoint survive a HA restart."""
    mock_restore_cache(
        hass,
        [
            State(
                CLIMATE_ENTITY_ID,
                HVACMode.HEAT,
                {ATTR_TEMPERATURE: 22.0, ATTR_PRESET_MODE: "none"},
            )
        ],
    )
    await async_setup_base(hass, temperature=19.0)
    await _setup(hass)

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 22.0
    assert hass.states.get(HEATER).state == "on"
