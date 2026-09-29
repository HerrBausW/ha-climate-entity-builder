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
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    AreaSelector,
    DurationSelector,
    DurationSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    IconSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_AREA,
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
    DEFAULT_COLD_TOLERANCE,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_ECO_TEMP,
    DEFAULT_HOT_TOLERANCE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_PROFILE_TEMPERATURE,
    DEFAULT_SENSOR_MAX_VALID_TEMP,
    DEFAULT_SENSOR_MIN_VALID_TEMP,
    DEFAULT_SENSOR_STALE_TIMEOUT_MINUTES,
    DEFAULT_TARGET_TEMP_STEP,
    DEFAULT_WINDOW_OPEN_TEMPERATURE,
    DOMAIN,
    RESERVED_PRESET_NAMES,
    SUBENTRY_TYPE_PROFILE,
    SUBENTRY_TYPE_THERMOSTAT,
)

# Switches and input_booleans are both turned on/off through the generic
# `homeassistant.turn_on` / `turn_off` services, which keeps the door open for
# future actuator domains (e.g. fans) without touching the control logic.
HEATER_DOMAINS = ["switch", "input_boolean"]


def _thermostat_data_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the (sub)entry schema, pre-filled with existing values if any.

    Fields that `_validate` can attach an error to (name, min/max temp,
    sensor min/max valid) are kept flat/top-level rather than inside a
    section: a section's nested fields aren't shown a per-field error by the
    current HA frontend (its inner <ha-form> isn't given the errors object
    at all), so an error on one of those would otherwise silently vanish
    instead of being shown to the user.
    """

    def d(key: str, fallback: Any) -> Any:
        return defaults.get(key, fallback)

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d(CONF_NAME, "")): cv.string,
            # A suggestion only: applied to the device just once, on first
            # creation, and never overrides a later manual area change on
            # the device page (see RoomThermostatClimate._async_maybe_set_area
            # in climate.py).
            vol.Optional(CONF_AREA, default=d(CONF_AREA, None)): vol.Any(
                None, AreaSelector()
            ),
            vol.Required(CONF_TEMP_SENSOR, default=d(CONF_TEMP_SENSOR, None)): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Required(CONF_HEATER, default=d(CONF_HEATER, None)): EntitySelector(
                EntitySelectorConfig(domain=HEATER_DOMAINS)
            ),
            # A plain extra sensor reading on the entity, unrelated to any
            # other field - kept flat/top-level with the other "what
            # hardware makes up this thermostat" fields above, rather than
            # sectioned with something it has no actual connection to.
            vol.Optional(
                CONF_HUMIDITY_SENSOR, default=d(CONF_HUMIDITY_SENSOR, None)
            ): vol.Any(
                None,
                EntitySelector(EntitySelectorConfig(domain="sensor", device_class="humidity")),
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
            vol.Required("hysteresis"): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_TARGET_TEMP_STEP,
                            default=d(CONF_TARGET_TEMP_STEP, DEFAULT_TARGET_TEMP_STEP),
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=0.1,
                                max=5,
                                step=0.1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                        vol.Required(
                            CONF_COLD_TOLERANCE,
                            default=d(CONF_COLD_TOLERANCE, DEFAULT_COLD_TOLERANCE),
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=0,
                                max=5,
                                step=0.1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                        vol.Required(
                            CONF_HOT_TOLERANCE,
                            default=d(CONF_HOT_TOLERANCE, DEFAULT_HOT_TOLERANCE),
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=0,
                                max=5,
                                step=0.1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                        vol.Optional(
                            CONF_MIN_CYCLE_DURATION, default=d(CONF_MIN_CYCLE_DURATION, None)
                        ): vol.Any(
                            None, DurationSelector(DurationSelectorConfig(enable_day=False))
                        ),
                    }
                ),
                {"collapsed": True},
            ),
            vol.Required("window_pause"): section(
                vol.Schema(
                    {
                        # A multi-entity EntitySelector's default must be a
                        # list, never None: some HA frontend versions submit
                        # "nothing selected" as null rather than [], and a
                        # previously-saved null default (present key, not
                        # missing) silently breaks *just this field's*
                        # rendering in Reconfigure. `.get(key, [])` alone
                        # doesn't guard against that, since the fallback only
                        # applies when the key is absent, not when it's
                        # present with value None.
                        vol.Optional(
                            CONF_WINDOW_SENSORS, default=d(CONF_WINDOW_SENSORS, []) or []
                        ): EntitySelector(
                            EntitySelectorConfig(
                                domain="binary_sensor", multiple=True, reorder=True
                            )
                        ),
                        vol.Optional(
                            CONF_WINDOW_OPEN_DELAY, default=d(CONF_WINDOW_OPEN_DELAY, None)
                        ): vol.Any(
                            None, DurationSelector(DurationSelectorConfig(enable_day=False))
                        ),
                        vol.Required(
                            CONF_WINDOW_OPEN_TEMPERATURE,
                            default=d(
                                CONF_WINDOW_OPEN_TEMPERATURE, DEFAULT_WINDOW_OPEN_TEMPERATURE
                            ),
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=-20,
                                max=50,
                                step=0.5,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("presets"): section(
                vol.Schema(
                    {
                        # The schedule decides which of these two the
                        # thermostat uses in auto mode, so it's grouped with
                        # them rather than with the unrelated humidity
                        # sensor it used to sit next to.
                        vol.Optional(
                            CONF_SCHEDULE, default=d(CONF_SCHEDULE, None)
                        ): vol.Any(None, EntitySelector(EntitySelectorConfig(domain="schedule"))),
                        vol.Required(
                            CONF_COMFORT_TEMP,
                            default=d(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP),
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=-20,
                                max=50,
                                step=0.5,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                        vol.Required(
                            CONF_ECO_TEMP, default=d(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=-20,
                                max=50,
                                step=0.5,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="°C",
                            )
                        ),
                    }
                ),
                {"collapsed": False},
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


_THERMOSTAT_SECTION_KEYS = ("hysteresis", "window_pause", "presets")


def _flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Merge each section's nested values back into one flat dict.

    A sectioned field is submitted (and needs pre-filling on redisplay) as
    `user_input["section_key"] = {"inner_field": value, ...}` rather than
    flat - flatten it back so the rest of this module can keep treating
    subentry data as a single flat dict, matching what's actually stored.
    """
    flat = dict(user_input)
    for key in _THERMOSTAT_SECTION_KEYS:
        section_values = flat.pop(key, None)
        if section_values:
            flat.update(section_values)
    return flat


def _duplicate_name_error(
    name: str,
    entry: ConfigEntry,
    *,
    subentry_type: str,
    ignore_subentry_id: str | None,
) -> str | None:
    """Return "name_exists" if another subentry of the same type has this name."""
    for subentry in entry.subentries.values():
        if subentry.subentry_type != subentry_type:
            continue
        if subentry.subentry_id == ignore_subentry_id:
            continue
        if subentry.data.get(CONF_NAME, "").casefold() == name.casefold():
            return "name_exists"
    return None


def _validate(
    user_input: dict[str, Any], entry: ConfigEntry, *, ignore_subentry_id: str | None
) -> dict[str, str]:
    """Return a dict of field -> error code, empty if valid."""

    errors: dict[str, str] = {}
    name = user_input[CONF_NAME].strip()
    if not name:
        errors[CONF_NAME] = "name_required"
    else:
        error = _duplicate_name_error(
            name,
            entry,
            subentry_type=SUBENTRY_TYPE_THERMOSTAT,
            ignore_subentry_id=ignore_subentry_id,
        )
        if error:
            errors[CONF_NAME] = error

    if user_input[CONF_MIN_TEMP] >= user_input[CONF_MAX_TEMP]:
        errors[CONF_MAX_TEMP] = "min_max_invalid"

    sensor_min = user_input[CONF_SENSOR_MIN_VALID]
    sensor_max = user_input[CONF_SENSOR_MAX_VALID]
    if sensor_min >= sensor_max:
        errors[CONF_SENSOR_MAX_VALID] = "min_max_invalid"

    return errors


def _validate_profile(
    user_input: dict[str, Any], entry: ConfigEntry, *, ignore_subentry_id: str | None
) -> dict[str, str]:
    """Return a dict of field -> error code, empty if valid."""

    errors: dict[str, str] = {}
    name = user_input[CONF_NAME].strip()
    if not name:
        errors[CONF_NAME] = "name_required"
    elif name.casefold() in RESERVED_PRESET_NAMES:
        errors[CONF_NAME] = "name_reserved"
    else:
        error = _duplicate_name_error(
            name,
            entry,
            subentry_type=SUBENTRY_TYPE_PROFILE,
            ignore_subentry_id=ignore_subentry_id,
        )
        if error:
            errors[CONF_NAME] = error

    return errors


def _profile_data_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the profile (sub)entry schema, pre-filled if reconfiguring."""

    def d(key: str, fallback: Any) -> Any:
        return defaults.get(key, fallback)

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d(CONF_NAME, "")): cv.string,
            vol.Required(
                CONF_PROFILE_TEMPERATURE,
                default=d(CONF_PROFILE_TEMPERATURE, DEFAULT_PROFILE_TEMPERATURE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-20, max=50, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C"
                )
            ),
            # Shown on the climate entity itself (sidebar, history graph,
            # more-info header) while this profile is the active preset - a
            # per-value icon in the preset picker's own dropdown row isn't
            # possible for a dynamically-named preset like this one.
            vol.Optional(
                CONF_PROFILE_ICON, default=d(CONF_PROFILE_ICON, None)
            ): vol.Any(None, IconSelector()),
        }
    )


class RoomThermostatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Climate Entity Builder hub config flow.

    Multiple hubs are allowed on purpose: each hub owns its own independent
    set of profile subentries, so e.g. a "Ground floor" hub and an "Upper
    floor" hub can offer different custom presets to the thermostats
    created under each of them.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a hub entry; thermostats/profiles are added as subentries."""
        if user_input is not None:
            name = user_input[CONF_NAME].strip() or "Climate Entity Builder"
            return self.async_create_entry(title=name, data={})

        default_name = "Climate Entity Builder" if not self._async_current_entries() else ""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=default_name): cv.string}),
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            SUBENTRY_TYPE_THERMOSTAT: ThermostatSubentryFlowHandler,
            SUBENTRY_TYPE_PROFILE: ProfileSubentryFlowHandler,
        }


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

        flat_input = _flatten_sections(user_input) if user_input is not None else None

        if flat_input is not None:
            errors = _validate(
                flat_input,
                entry,
                ignore_subentry_id=existing.subentry_id if existing else None,
            )
            if not errors:
                name = flat_input[CONF_NAME].strip()
                data = {
                    **flat_input,
                    CONF_NAME: name,
                    # Never persist None for the multi-select: a saved null
                    # here (rather than a missing key) breaks this field's
                    # rendering on the next Reconfigure.
                    CONF_WINDOW_SENSORS: flat_input.get(CONF_WINDOW_SENSORS) or [],
                }
                if existing is not None:
                    return self.async_update_and_abort(entry, existing, data=data, title=name)
                return self.async_create_entry(title=name, data=data)

        defaults = dict(existing.data) if existing else dict(flat_input or {})
        schema = _thermostat_data_schema(defaults)
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=schema,
            errors=errors,
        )


class ProfileSubentryFlowHandler(ConfigSubentryFlow):
    """Add or reconfigure a custom preset profile (name + temperature).

    Every profile under a hub is offered as an extra selectable preset (in
    heat mode) on every thermostat under that same hub - a room simply can't
    see another hub's profiles, since each subentry only ever belongs to
    one parent hub.
    """

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new profile."""
        return await self._async_step(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing profile."""
        return await self._async_step(user_input)

    async def _async_step(
        self, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        reconfigure = self.source == SOURCE_RECONFIGURE
        existing = self._get_reconfigure_subentry() if reconfigure else None
        entry = self._get_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_profile(
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
        schema = _profile_data_schema(defaults)
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=schema,
            errors=errors,
        )
