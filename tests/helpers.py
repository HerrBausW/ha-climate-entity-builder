"""Shared helpers for Room Thermostat tests."""

from __future__ import annotations

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.room_thermostat.const import (
    CONF_COLD_TOLERANCE,
    CONF_COMFORT_TEMP,
    CONF_ECO_TEMP,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_HUMIDITY_SENSOR,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_NAME,
    CONF_SCHEDULE,
    CONF_SENSOR_MAX_VALID,
    CONF_SENSOR_MIN_VALID,
    CONF_SENSOR_STALE_TIMEOUT,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMP_SENSOR,
    DOMAIN,
    SUBENTRY_TYPE_THERMOSTAT,
)

TEMP_SENSOR = "sensor.schlafzimmer_temperatur"
HUMIDITY_SENSOR = "sensor.schlafzimmer_luftfeuchtigkeit"
HEATER = "switch.schlafzimmer_heizventil"
SCHEDULE = "schedule.heizung_schlafzimmer"


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


def thermostat_subentry(**overrides: Any) -> dict[str, Any]:
    """Return a subentries_data entry for MockConfigEntry."""
    data = thermostat_data(**overrides)
    return {
        "data": data,
        "subentry_type": SUBENTRY_TYPE_THERMOSTAT,
        "title": data[CONF_NAME],
        "unique_id": None,
    }


def make_hub_entry(*, subentries: list[dict[str, Any]] | None = None) -> MockConfigEntry:
    """Return a MockConfigEntry for the Room Thermostat hub."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Room Thermostat",
        data={},
        subentries_data=subentries or [],
    )


def set_base_states(hass, *, temperature: float = 19.0, humidity: float = 45.0) -> None:
    """Seed the sensors/switch/schedule this thermostat depends on."""
    hass.states.async_set(TEMP_SENSOR, str(temperature))
    hass.states.async_set(HUMIDITY_SENSOR, str(humidity))
    hass.states.async_set(HEATER, "off")
    hass.states.async_set(SCHEDULE, "off")
