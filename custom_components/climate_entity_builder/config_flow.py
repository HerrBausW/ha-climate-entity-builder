"""Config flow for the Climate Entity Builder integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    DurationSelector,
    DurationSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
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
    CONF_SCHEDULE,
    CONF_SENSOR_MAX_VALID,
    CONF_SENSOR_MIN_VALID,
    CONF_SENSOR_STALE_TIMEOUT,
    CONF_TARGET_TEMP_STEP,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_OPEN_DELAY,
    CONF_WINDOW_SENSORS,
    CONF_FROST_PROTECTION_TEMP,
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_ECO_TEMP,
    DEFAULT_FROST_PROTECTION_TEMP,
    DEFAULT_HOT_TOLERANCE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_SENSOR_MAX_VALID_TEMP,
    DEFAULT_SENSOR_MIN_VALID_TEMP,
    DEFAULT_SENSOR_STALE_TIMEOUT_MINUTES,
    DEFAULT_TARGET_TEMP_STEP,
    DOMAIN,
    SUBENTRY_TYPE_THERMOSTAT,
)

# device_class filter for the window/door contacts that pause heating.
WINDOW_SENSOR_DEVICE_CLASSES = ["window", "door", "garage_door", "opening"]

# Switches and input_booleans are both turned on/off through the generic
# `homeassistant.turn_on` / `turn_off` services, which keeps the door open for
# future actuator domains (e.g. fans) without touching the control logic.
HEATER_DOMAINS = ["switch", "input_boolean"]


def _thermostat_data_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the (sub)entry schema, pre-filled with existing values if any."""

    def d(key: str, fallback: Any) -> Any:
        return defaults.get(key, fallback)

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d(CONF_NAME, "")): cv.string,
            vol.Required(CONF_TEMP_SENSOR, default=d(CONF_TEMP_SENSOR, None)): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Required(CONF_HEATER, default=d(CONF_HEATER, None)): EntitySelector(
                EntitySelectorConfig(domain=HEATER_DOMAINS)
            ),
            vol.Optional(
                CONF_HUMIDITY_SENSOR, default=d(CONF_HUMIDITY_SENSOR, None)
            ): vol.Any(
                None,
                EntitySelector(EntitySelectorConfig(domain="sensor", device_class="humidity")),
            ),
            vol.Optional(CONF_SCHEDULE, default=d(CONF_SCHEDULE, None)): vol.Any(
                None, EntitySelector(EntitySelectorConfig(domain="schedule"))
            ),
            vol.Required(
                CONF_MIN_TEMP, default=d(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_MAX_TEMP, default=d(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_TARGET_TEMP_STEP,
                default=d(CONF_TARGET_TEMP_STEP, DEFAULT_TARGET_TEMP_STEP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1, max=5, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_COLD_TOLERANCE,
                default=d(CONF_COLD_TOLERANCE, DEFAULT_COLD_TOLERANCE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=5, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_HOT_TOLERANCE,
                default=d(CONF_HOT_TOLERANCE, DEFAULT_HOT_TOLERANCE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=5, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Optional(
                CONF_MIN_CYCLE_DURATION, default=d(CONF_MIN_CYCLE_DURATION, None)
            ): vol.Any(None, DurationSelector(DurationSelectorConfig(enable_day=False))),
            vol.Optional(
                CONF_WINDOW_SENSORS, default=d(CONF_WINDOW_SENSORS, None)
            ): vol.Any(
                None,
                EntitySelector(
                    EntitySelectorConfig(
                        domain="binary_sensor",
                        device_class=WINDOW_SENSOR_DEVICE_CLASSES,
                        multiple=True,
                    )
                ),
            ),
            vol.Optional(
                CONF_WINDOW_OPEN_DELAY, default=d(CONF_WINDOW_OPEN_DELAY, None)
            ): vol.Any(None, DurationSelector(DurationSelectorConfig(enable_day=False))),
            vol.Required(
                CONF_FROST_PROTECTION_TEMP,
                default=d(CONF_FROST_PROTECTION_TEMP, DEFAULT_FROST_PROTECTION_TEMP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_COMFORT_TEMP, default=d(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_ECO_TEMP, default=d(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_SENSOR_STALE_TIMEOUT,
                default=d(CONF_SENSOR_STALE_TIMEOUT, DEFAULT_SENSOR_STALE_TIMEOUT_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=180, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min"
                )
            ),
            vol.Required(
                CONF_SENSOR_MIN_VALID,
                default=d(CONF_SENSOR_MIN_VALID, DEFAULT_SENSOR_MIN_VALID_TEMP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-40, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            vol.Required(
                CONF_SENSOR_MAX_VALID,
                default=d(CONF_SENSOR_MAX_VALID, DEFAULT_SENSOR_MAX_VALID_TEMP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-40, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
        }
    )


def _validate(
    user_input: dict[str, Any], entry: ConfigEntry, *, ignore_subentry_id: str | None
) -> dict[str, str]:
    """Return a dict of field -> error code, empty if valid."""

    errors: dict[str, str] = {}
    name = user_input[CONF_NAME].strip()
    if not name:
        errors[CONF_NAME] = "name_required"
    else:
        for subentry in entry.subentries.values():
            if subentry.subentry_id == ignore_subentry_id:
                continue
            if subentry.data.get(CONF_NAME, "").casefold() == name.casefold():
                errors[CONF_NAME] = "name_exists"
                break

    if user_input[CONF_MIN_TEMP] >= user_input[CONF_MAX_TEMP]:
        errors[CONF_MAX_TEMP] = "min_max_invalid"

    sensor_min = user_input[CONF_SENSOR_MIN_VALID]
    sensor_max = user_input[CONF_SENSOR_MAX_VALID]
    if sensor_min >= sensor_max:
        errors[CONF_SENSOR_MAX_VALID] = "min_max_invalid"

    return errors


class RoomThermostatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the (single-instance) Climate Entity Builder hub config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single hub entry; thermostats are added as subentries."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Climate Entity Builder", data={})

        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_THERMOSTAT: ThermostatSubentryFlowHandler}


class ThermostatSubentryFlowHandler(ConfigSubentryFlow):
    """Add or reconfigure a single room thermostat."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new thermostat."""
        return await self._async_step(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing thermostat."""
        return await self._async_step(user_input)

    async def _async_step(
        self, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        reconfigure = self.source == SOURCE_RECONFIGURE
        existing = self._get_reconfigure_subentry() if reconfigure else None
        entry = self._get_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate(
                user_input,
                entry,
                ignore_subentry_id=existing.subentry_id if existing else None,
            )
            if not errors:
                name = user_input[CONF_NAME].strip()
                data = {**user_input, CONF_NAME: name}
                if existing is not None:
                    return self.async_update_and_abort(entry, existing, data=data, title=name)
                return self.async_create_entry(title=name, data=data)

        defaults = dict(existing.data) if existing else dict(user_input or {})
        schema = _thermostat_data_schema(defaults)
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=schema,
            errors=errors,
        )
