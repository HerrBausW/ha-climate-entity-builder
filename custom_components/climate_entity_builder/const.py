"""Constants for the Climate Entity Builder integration."""

from __future__ import annotations

from homeassistant.components.climate import PRESET_COMFORT, PRESET_ECO

DOMAIN = "climate_entity_builder"

SUBENTRY_TYPE_THERMOSTAT = "thermostat"

# --- Config / subentry data keys -------------------------------------------------

CONF_NAME = "name"
CONF_TEMP_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_HEATER = "heater"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP_STEP = "target_temp_step"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_MIN_CYCLE_DURATION = "min_cycle_duration"
CONF_SCHEDULE = "schedule_entity"
CONF_COMFORT_TEMP = "comfort_temperature"
CONF_ECO_TEMP = "eco_temperature"
CONF_SENSOR_STALE_TIMEOUT = "sensor_stale_timeout"
CONF_SENSOR_MIN_VALID = "sensor_min_valid_temp"
CONF_SENSOR_MAX_VALID = "sensor_max_valid_temp"
CONF_WINDOW_SENSOR = "window_sensor"
CONF_WINDOW_OPEN_DELAY = "window_open_delay"
CONF_FROST_PROTECTION_TEMP = "frost_protection_temperature"

# --- Defaults ----------------------------------------------------------------

DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 30.5
DEFAULT_TARGET_TEMP_STEP = 0.5
DEFAULT_COLD_TOLERANCE = 0.2
DEFAULT_HOT_TOLERANCE = 0.2
DEFAULT_COMFORT_TEMP = 21.0
DEFAULT_ECO_TEMP = 18.0
DEFAULT_SENSOR_STALE_TIMEOUT_MINUTES = 15
DEFAULT_SENSOR_MIN_VALID_TEMP = 5.0
DEFAULT_SENSOR_MAX_VALID_TEMP = 40.0
DEFAULT_FROST_PROTECTION_TEMP = 7.0

# --- Presets -------------------------------------------------------------------
# Presets are only ever offered while hvac_mode == HEAT. In AUTO mode the
# schedule is the sole source of truth for the effective target temperature,
# so presets are hidden there to avoid two competing ways to pick a setpoint.

PRESET_COMFORT_MODE = PRESET_COMFORT
PRESET_ECO_MODE = PRESET_ECO

# A window sensor pause is shown via this preset (not user-selectable, only
# ever returned while a configured window/door sensor is open) instead of
# forcing hvac_action to "off", so the thermostat keeps regulating against
# the frost protection temperature rather than going fully inert.
PRESET_FROST_PROTECTION = "frost_protection"

# --- Runtime state / attributes -------------------------------------------------

ATTR_EFFECTIVE_TARGET_TEMPERATURE = "effective_target_temperature"
ATTR_FAILSAFE_ACTIVE = "failsafe_active"
ATTR_WINDOW_OPEN = "window_open"
DATA_FAILSAFE_STATES = "failsafe_states"
DATA_WINDOW_OPEN_STATES = "window_open_states"


def failsafe_signal(subentry_id: str) -> str:
    """Return the dispatcher signal for a thermostat failsafe state."""
    return f"{DOMAIN}_failsafe_{subentry_id}"


def window_open_signal(subentry_id: str) -> str:
    """Return the dispatcher signal for a thermostat's window-open state."""
    return f"{DOMAIN}_window_open_{subentry_id}"


MANUFACTURER = "Climate Entity Builder"
