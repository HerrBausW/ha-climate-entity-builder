"""Shared helpers for Climate Entity Builder tests."""

from __future__ import annotations

from typing import Any

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_entity_builder.const import (
    CONF_COLD_TOLERANCE,
    CONF_COMFORT_TEMP,
    CONF_ECO_TEMP,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_HUMIDITY_SENSOR,
    CONF_MAX_TEMP,
    CONF_MIN_CYCLE_DURATION,
    CONF_MIN_TEMP,
    CONF_NAME,
    CONF_PROFILE_ICON,
    CONF_PROFILE_TEMPERATURE,
    CONF_SCHEDULE,
    CONF_SENSOR_MAX_VALID,
    CONF_SENSOR_MIN_VALID,
    CONF_SENSOR_STALE_TIMEOUT,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_OPEN_DELAY,
    CONF_WINDOW_OPEN_TEMPERATURE,
    CONF_WINDOW_SENSORS,
    DEFAULT_WINDOW_OPEN_TEMPERATURE,
    DOMAIN,
    SUBENTRY_TYPE_PROFILE,
    SUBENTRY_TYPE_THERMOSTAT,
)

TEMP_SENSOR = "sensor.schlafzimmer_temperatur"
HUMIDITY_SENSOR = "sensor.schlafzimmer_luftfeuchtigkeit"
HEATER = "input_boolean.schlafzimmer_heizventil"
SCHEDULE = "schedule.heizung_schlafzimmer"
WINDOW_SENSOR = "binary_sensor.schlafzimmer_fenster_links"
WINDOW_SENSOR_2 = "binary_sensor.schlafzimmer_fenster_rechts"


def thermostat_data(**overrides: Any) -> dict[str, Any]:
    """Return a complete, valid thermostat subentry data dict."""
    data: dict[str, Any] = {
        CONF_NAME: "Schlafzimmer",
        CONF_TEMP_SENSOR: TEMP_SENSOR,
        CONF_HEATER: HEATER,
        CONF_HUMIDITY_SENSOR: HUMIDITY_SENSOR,
        CONF_SCHEDULE: SCHEDULE,
        CONF_MIN_TEMP: 5.0,
        CONF_MAX_TEMP: 30.5,
        CONF_TARGET_TEMP_STEP: 0.5,
        CONF_COLD_TOLERANCE: 0.2,
        CONF_HOT_TOLERANCE: 0.2,
        CONF_COMFORT_TEMP: 21.0,
        CONF_ECO_TEMP: 18.0,
        CONF_SENSOR_STALE_TIMEOUT: 15,
        CONF_SENSOR_MIN_VALID: 5.0,
        CONF_SENSOR_MAX_VALID: 40.0,
    }
    data.update(overrides)
    return data


def sectioned_thermostat_data(**overrides: Any) -> dict[str, Any]:
    """Return a thermostat form submission shaped like the real, sectioned schema.

    Fields that can carry a validation error (name, min/max temp, sensor
    min/max valid) stay flat, matching `_thermostat_data_schema`; everything
    else is nested under its section key, exactly as the frontend submits it.
    """
    flat = thermostat_data(**overrides)
    return {
        CONF_NAME: flat[CONF_NAME],
        CONF_TEMP_SENSOR: flat[CONF_TEMP_SENSOR],
        CONF_HEATER: flat[CONF_HEATER],
        "sensors_schedule": {
            CONF_HUMIDITY_SENSOR: flat.get(CONF_HUMIDITY_SENSOR),
            CONF_SCHEDULE: flat.get(CONF_SCHEDULE),
        },
        CONF_MIN_TEMP: flat[CONF_MIN_TEMP],
        CONF_MAX_TEMP: flat[CONF_MAX_TEMP],
        "hysteresis": {
            CONF_TARGET_TEMP_STEP: flat[CONF_TARGET_TEMP_STEP],
            CONF_COLD_TOLERANCE: flat[CONF_COLD_TOLERANCE],
            CONF_HOT_TOLERANCE: flat[CONF_HOT_TOLERANCE],
            CONF_MIN_CYCLE_DURATION: flat.get(CONF_MIN_CYCLE_DURATION),
        },
        "window_pause": {
            CONF_WINDOW_SENSORS: flat.get(CONF_WINDOW_SENSORS) or [],
            CONF_WINDOW_OPEN_DELAY: flat.get(CONF_WINDOW_OPEN_DELAY),
            CONF_WINDOW_OPEN_TEMPERATURE: flat.get(
                CONF_WINDOW_OPEN_TEMPERATURE, DEFAULT_WINDOW_OPEN_TEMPERATURE
            ),
        },
        "presets": {
            CONF_COMFORT_TEMP: flat[CONF_COMFORT_TEMP],
            CONF_ECO_TEMP: flat[CONF_ECO_TEMP],
        },
        CONF_SENSOR_STALE_TIMEOUT: flat[CONF_SENSOR_STALE_TIMEOUT],
        CONF_SENSOR_MIN_VALID: flat[CONF_SENSOR_MIN_VALID],
        CONF_SENSOR_MAX_VALID: flat[CONF_SENSOR_MAX_VALID],
    }


def thermostat_subentry(**overrides: Any) -> dict[str, Any]:
    """Return a subentries_data entry for MockConfigEntry."""
    data = thermostat_data(**overrides)
    return {
        "data": data,
        "subentry_type": SUBENTRY_TYPE_THERMOSTAT,
        "title": data[CONF_NAME],
        "unique_id": None,
    }


def profile_subentry(
    name: str, temperature: float, *, icon: str | None = None
) -> dict[str, Any]:
    """Return a profile subentries_data entry for MockConfigEntry."""
    return {
        "data": {
            CONF_NAME: name,
            CONF_PROFILE_TEMPERATURE: temperature,
            CONF_PROFILE_ICON: icon,
        },
        "subentry_type": SUBENTRY_TYPE_PROFILE,
        "title": name,
        "unique_id": None,
    }


def make_hub_entry(*, subentries: list[dict[str, Any]] | None = None) -> MockConfigEntry:
    """Return a MockConfigEntry for the Climate Entity Builder hub."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Climate Entity Builder",
        data={},
        subentries_data=subentries or [],
    )


async def async_setup_base(hass, *, temperature: float = 19.0, humidity: float = 45.0) -> None:
    """Seed the sensors/schedule and a *real* heater entity this thermostat depends on.

    The heater must be a real entity (not just a bare state) so that the
    homeassistant.turn_on/turn_off services the integration calls actually do
    something, exactly like generic_thermostat's own test suite sets up a
    real switch/input_boolean instead of faking the state.
    """
    assert await async_setup_component(
        hass, "input_boolean", {"input_boolean": {HEATER.split(".")[1]: None}}
    )
    await hass.async_block_till_done()
    hass.states.async_set(TEMP_SENSOR, str(temperature))
    hass.states.async_set(HUMIDITY_SENSOR, str(humidity))
    hass.states.async_set(SCHEDULE, "off")
