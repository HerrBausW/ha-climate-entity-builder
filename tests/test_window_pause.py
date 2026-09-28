"""Tests for window/door contacts pausing heating to the eco/setback target."""

from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.components.climate import ATTR_PRESET_MODE, HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.climate_entity_builder.const import (
    ATTR_WINDOW_OPEN,
    DOMAIN,
    PRESET_WINDOW_OPEN,
)

from .helpers import (
    HEATER,
    TEMP_SENSOR,
    WINDOW_SENSOR,
    WINDOW_SENSOR_2,
    async_setup_base,
    make_hub_entry,
    thermostat_subentry,
)

CLIMATE_ENTITY_ID = "climate.schlafzimmer"


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


async def test_window_open_switches_to_eco_temperature(hass) -> None:
    """Item: opening a window pauses heating at the eco/setback target."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(hass, window_sensors=[WINDOW_SENSOR])
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] == 18.0
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_WINDOW_OPEN
    assert state.attributes[ATTR_WINDOW_OPEN] is True
    # 19 °C is above the 18 °C eco target, so heating stays off.
    assert hass.states.get(HEATER).state == "off"


async def test_window_open_preset_is_listed_only_while_active(hass) -> None:
    """The climate card can't render/highlight a preset absent from preset_modes.

    window_open must appear in preset_modes while the pause is active (so
    the card's chip actually shows it instead of silently defaulting to
    "none"), and disappear again once the window closes.
    """
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(hass, window_sensors=[WINDOW_SENSOR])
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert PRESET_WINDOW_OPEN not in state.attributes["preset_modes"]

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert PRESET_WINDOW_OPEN in state.attributes["preset_modes"]
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_WINDOW_OPEN

    hass.states.async_set(WINDOW_SENSOR, "off")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert PRESET_WINDOW_OPEN not in state.attributes["preset_modes"]


async def test_window_open_preset_cannot_be_set_manually(hass) -> None:
    """It's shown for information only - selecting it via the service must fail."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "on")
    await _setup(hass, window_sensors=[WINDOW_SENSOR])
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {
                "entity_id": CLIMATE_ENTITY_ID,
                ATTR_PRESET_MODE: PRESET_WINDOW_OPEN,
            },
            blocking=True,
        )


async def test_second_window_sensor_also_triggers_pause(hass) -> None:
    """Item: with two configured sensors, either one opening pauses heating."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    hass.states.async_set(WINDOW_SENSOR_2, "off")
    await _setup(hass, window_sensors=[WINDOW_SENSOR, WINDOW_SENSOR_2])
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    # only the second sensor opens; the first stays closed
    hass.states.async_set(WINDOW_SENSOR_2, "on")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_WINDOW_OPEN] is True
    assert state.attributes[ATTR_TEMPERATURE] == 18.0

    # closing it (while the first is still closed) resumes normal control
    hass.states.async_set(WINDOW_SENSOR_2, "off")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_WINDOW_OPEN] is False
    assert state.attributes[ATTR_TEMPERATURE] == 21.0


async def test_window_close_restores_previous_setpoint(hass) -> None:
    """Item: closing the window reverts to the setpoint that was active before."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(hass, window_sensors=[WINDOW_SENSOR])
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"

    hass.states.async_set(WINDOW_SENSOR, "off")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] == 21.0
    assert state.attributes[ATTR_PRESET_MODE] == "none"
    assert state.attributes[ATTR_WINDOW_OPEN] is False
    assert hass.states.get(HEATER).state == "on"


async def test_window_open_ignored_while_hvac_off(hass) -> None:
    """Item: an open window must not force heating on when the mode is off."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(hass, window_sensors=[WINDOW_SENSOR])
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert hass.states.get(HEATER).state == "off"


async def test_brief_window_opening_within_delay_is_ignored(hass) -> None:
    """Item: a short opening inside the configured delay never pauses heating."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(
        hass, window_sensors=[WINDOW_SENSOR], window_open_delay={"minutes": 5}
    )
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()
    hass.states.async_set(WINDOW_SENSOR, "off")
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_WINDOW_OPEN] is False
    assert state.attributes[ATTR_TEMPERATURE] == 21.0
    assert hass.states.get(HEATER).state == "on"


async def test_window_open_past_delay_pauses_heating(hass) -> None:
    """Item: once a window stays open past the delay, the pause engages."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    await _setup(
        hass, window_sensors=[WINDOW_SENSOR], window_open_delay={"minutes": 5}
    )
    await _set_hvac_mode(hass, HVACMode.HEAT)
    await _set_temperature(hass, 21.0)
    await hass.async_block_till_done()

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()
    # still within the delay: no change yet
    assert hass.states.get(CLIMATE_ENTITY_ID).attributes[ATTR_WINDOW_OPEN] is False

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_WINDOW_OPEN] is True
    assert state.attributes[ATTR_TEMPERATURE] == 18.0


async def test_window_open_binary_sensor_mirrors_state(hass) -> None:
    """Item: the companion window_open binary sensor tracks the debounced state."""
    await async_setup_base(hass, temperature=19.0)
    hass.states.async_set(WINDOW_SENSOR, "off")
    entry = await _setup(hass, window_sensors=[WINDOW_SENSOR])
    subentry_id = next(iter(entry.subentries))

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{subentry_id}_window_open"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "off"

    hass.states.async_set(WINDOW_SENSOR, "on")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "on"
