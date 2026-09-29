"""Climate platform for the Climate Entity Builder integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util

from .const import (
    ATTR_EFFECTIVE_TARGET_TEMPERATURE,
    ATTR_FAILSAFE_ACTIVE,
    ATTR_WINDOW_OPEN,
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
    CONF_WINDOW_OPEN_PROFILE,
    CONF_WINDOW_SENSORS,
    DATA_FAILSAFE_STATES,
    DATA_WINDOW_OPEN_STATES,
    DOMAIN,
    MANUFACTURER,
    PRESET_WINDOW_OPEN,
    SUBENTRY_TYPE_PROFILE,
    SUBENTRY_TYPE_THERMOSTAT,
    failsafe_signal,
    window_open_signal,
)

_LOGGER = logging.getLogger(__name__)

HA_DOMAIN = "homeassistant"


def _hub_profiles(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return this hub's profile subentries as plain dicts.

    A thermostat only ever sees the profiles of its own parent hub - each
    subentry belongs to exactly one config entry, so there's no way for a
    room under one hub to pick up another hub's profiles.
    """
    return [
        {
            "id": subentry.subentry_id,
            "name": subentry.data[CONF_NAME],
            "temperature": subentry.data[CONF_PROFILE_TEMPERATURE],
            "icon": subentry.data.get(CONF_PROFILE_ICON),
        }
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_PROFILE
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one climate entity per thermostat subentry."""
    profiles = _hub_profiles(entry)
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_THERMOSTAT:
            continue
        async_add_entities(
            [RoomThermostatClimate(subentry, profiles)], config_subentry_id=subentry_id
        )


class RoomThermostatClimate(ClimateEntity, RestoreEntity):
    """A virtual room thermostat built from existing HA entities."""

    _attr_has_entity_name = True
    _attr_name = None
    # Needed so the frontend can find our translated label for the custom
    # "window_open" preset value below (entity.climate.thermostat.
    # state_attributes.preset_mode.state.window_open). The standard
    # presets (none/comfort/eco) keep resolving via HA's own shared climate
    # translations regardless - this only adds the one we own.
    _attr_translation_key = "thermostat"
    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, subentry: ConfigSubentry, profiles: list[dict[str, Any]]) -> None:
        data = subentry.data
        # A profile's name doubles as its preset_mode value, so it's an
        # error to shadow a built-in one - already rejected at config time,
        # this is just the runtime side of that same guarantee.
        self._profiles = profiles
        name = data[CONF_NAME]
        self._subentry_id = subentry.subentry_id

        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Virtual Room Thermostat",
        )

        self._temp_sensor_entity_id: str = data[CONF_TEMP_SENSOR]
        self._humidity_sensor_entity_id: str | None = data.get(CONF_HUMIDITY_SENSOR)
        self._heater_entity_id: str = data[CONF_HEATER]
        self._schedule_entity_id: str | None = data.get(CONF_SCHEDULE)

        self._attr_min_temp: float = data[CONF_MIN_TEMP]
        self._attr_max_temp: float = data[CONF_MAX_TEMP]
        self._attr_target_temperature_step: float = data[CONF_TARGET_TEMP_STEP]
        self._cold_tolerance: float = data[CONF_COLD_TOLERANCE]
        self._hot_tolerance: float = data[CONF_HOT_TOLERANCE]
        self._comfort_temp: float = data[CONF_COMFORT_TEMP]
        self._eco_temp: float = data[CONF_ECO_TEMP]
        self._sensor_stale_timeout_minutes: float = data[CONF_SENSOR_STALE_TIMEOUT]
        self._sensor_min_valid: float = data[CONF_SENSOR_MIN_VALID]
        self._sensor_max_valid: float = data[CONF_SENSOR_MAX_VALID]

        raw_cycle = data.get(CONF_MIN_CYCLE_DURATION)
        self._min_cycle_duration: timedelta | None = (
            timedelta(**raw_cycle) if raw_cycle else None
        )

        self._window_sensor_entity_ids: list[str] = list(data.get(CONF_WINDOW_SENSORS) or [])
        raw_window_delay = data.get(CONF_WINDOW_OPEN_DELAY)
        self._window_open_delay: timedelta | None = (
            timedelta(**raw_window_delay) if raw_window_delay else None
        )
        # By stable subentry ID, not name, so renaming/reordering profiles
        # later never breaks this link. A stale/never-set ID (deleted
        # profile, or simply none picked) falls back to the eco temperature.
        self._window_open_profile_id: str | None = data.get(CONF_WINDOW_OPEN_PROFILE)
        self._attr_hvac_mode: HVACMode = HVACMode.OFF
        self._attr_target_temperature: float = self._comfort_temp
        self._attr_preset_mode: str = PRESET_NONE

        self._current_temp: float | None = None
        self._current_humidity: int | None = None
        self._sensor_valid = False
        self._failsafe_active = False
        self._failsafe_unsub: CALLBACK_TYPE | None = None
        self._window_open = False
        self._window_open_unsub: CALLBACK_TYPE | None = None
        self._last_decision = "init"

    # --- restore / setup -----------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore previous state and start listening for updates."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.state in (HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO):
                self._attr_hvac_mode = HVACMode(last_state.state)
            temp = last_state.attributes.get(ATTR_TEMPERATURE)
            if temp is not None:
                try:
                    self._attr_target_temperature = float(temp)
                except (TypeError, ValueError):
                    pass
            preset = last_state.attributes.get("preset_mode")
            # A restored profile name that no longer exists (renamed/removed
            # while HA was stopped) is simply not restored, falling back to
            # PRESET_NONE instead of a dangling reference.
            if preset in (PRESET_COMFORT, PRESET_ECO) or preset in self._profile_names():
                self._attr_preset_mode = preset

        self._handle_temperature_state(self.hass.states.get(self._temp_sensor_entity_id))
        if self._humidity_sensor_entity_id:
            self._handle_humidity_state(self.hass.states.get(self._humidity_sensor_entity_id))
        if self._window_sensor_entity_ids:
            self._handle_window_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._temp_sensor_entity_id], self._async_temp_sensor_changed
            )
        )
        if self._humidity_sensor_entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._humidity_sensor_entity_id],
                    self._async_humidity_sensor_changed,
                )
            )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._heater_entity_id], self._async_heater_changed
            )
        )
        if self._schedule_entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._schedule_entity_id], self._async_schedule_changed
                )
            )
        if self._window_sensor_entity_ids:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._window_sensor_entity_ids,
                    self._async_window_sensor_changed,
                )
            )
        self.async_on_remove(self._cancel_failsafe_timer)
        self.async_on_remove(self._cancel_window_open_timer)

        await self._async_control_heating()

    # --- HA climate properties -------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if self._schedule_entity_id:
            modes.append(HVACMode.AUTO)
        return modes

    @property
    def hvac_action(self) -> HVACAction:
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self._failsafe_active:
            return HVACAction.OFF
        return HVACAction.HEATING if self._is_heater_on() else HVACAction.IDLE

    @property
    def _window_pause_active(self) -> bool:
        return self._window_open and self._attr_hvac_mode != HVACMode.OFF

    def _profile_names(self) -> list[str]:
        return [profile["name"] for profile in self._profiles]

    def _profile_temperature(self, name: str) -> float | None:
        for profile in self._profiles:
            if profile["name"] == name:
                return profile["temperature"]
        return None

    def _profile_by_id(self, profile_id: str | None) -> dict[str, Any] | None:
        if profile_id is None:
            return None
        for profile in self._profiles:
            if profile["id"] == profile_id:
                return profile
        return None

    @property
    def preset_mode(self) -> str:
        # Only ever returned while a configured window/door sensor is
        # holding the thermostat at the eco/setback temperature. The
        # user's real preset/target underneath is untouched and reasserts
        # itself the moment the window closes.
        if self._window_pause_active:
            return PRESET_WINDOW_OPEN
        return self._attr_preset_mode

    @property
    def preset_modes(self) -> list[str]:
        if self._attr_hvac_mode == HVACMode.HEAT:
            modes = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, *self._profile_names()]
        else:
            modes = [PRESET_NONE]
        if self._window_pause_active:
            # Included only while active, so the climate card's preset chip
            # and picker can actually render/highlight it (a preset_mode
            # value absent from preset_modes isn't recognized by the
            # frontend and silently falls back to showing "none" selected).
            # Still not meant to be picked manually - async_set_preset_mode
            # rejects it below.
            modes = [*modes, PRESET_WINDOW_OPEN]
        return modes

    @property
    def icon(self) -> str | None:
        # A profile's own icon (if it has one) shows on the entity itself -
        # sidebar, history graph, more-info header - while it's the active
        # preset. There's no way to show it specifically in the preset
        # picker's own dropdown row for a dynamically-named preset like
        # this (see the profile subentry's icon field for why).
        profile = next(
            (p for p in self._profiles if p["name"] == self._attr_preset_mode), None
        )
        if profile is not None and not self._window_pause_active:
            return profile["icon"]
        return None

    @property
    def current_temperature(self) -> float | None:
        return self._current_temp

    @property
    def current_humidity(self) -> int | None:
        return self._current_humidity

    @property
    def target_temperature(self) -> float | None:
        return self._effective_target_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            ATTR_FAILSAFE_ACTIVE: self._failsafe_active,
            ATTR_WINDOW_OPEN: self._window_open,
        }
        if self._attr_hvac_mode == HVACMode.AUTO:
            attrs[ATTR_EFFECTIVE_TARGET_TEMPERATURE] = self._effective_target_temperature
        return attrs

    # --- HA climate services ----------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="hvac_mode_not_supported",
                translation_placeholders={"mode": hvac_mode},
            )
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.HEAT:
            self._attr_preset_mode = PRESET_NONE
        await self._async_control_heating()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if self._attr_hvac_mode == HVACMode.AUTO:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="auto_mode_temperature_readonly",
            )
        self._attr_target_temperature = temperature
        self._attr_preset_mode = PRESET_NONE
        await self._async_control_heating()
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_WINDOW_OPEN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="preset_mode_window_open_readonly",
            )
        if preset_mode not in self.preset_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="preset_mode_not_supported",
                translation_placeholders={"preset": preset_mode},
            )
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_COMFORT:
            self._attr_target_temperature = self._comfort_temp
        elif preset_mode == PRESET_ECO:
            self._attr_target_temperature = self._eco_temp
        else:
            profile_temperature = self._profile_temperature(preset_mode)
            if profile_temperature is not None:
                self._attr_target_temperature = profile_temperature
        await self._async_control_heating()
        self.async_write_ha_state()

    # --- sensor / actuator state handling ----------------------------------

    def _is_valid_temperature_state(self, state) -> float | None:
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        if value < self._sensor_min_valid or value > self._sensor_max_valid:
            return None
        return value

    def _set_failsafe_active(self, active: bool) -> None:
        """Publish the failsafe state for the companion binary sensor."""
        failsafe_states = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            DATA_FAILSAFE_STATES, {}
        )
        previous = failsafe_states.get(self._subentry_id)
        self._failsafe_active = active
        failsafe_states[self._subentry_id] = active
        if previous != active:
            async_dispatcher_send(self.hass, failsafe_signal(self._subentry_id))

    def _handle_temperature_state(self, state) -> None:
        value = self._is_valid_temperature_state(state)
        if value is not None:
            self._current_temp = value
            if not self._sensor_valid:
                _LOGGER.info("%s: temperature sensor is valid again", self.entity_id)
            self._sensor_valid = True
            self._cancel_failsafe_timer()
            self._set_failsafe_active(False)
        else:
            if self._sensor_valid:
                _LOGGER.warning(
                    "%s: temperature sensor %s is invalid, failsafe in %s minutes",
                    self.entity_id,
                    self._temp_sensor_entity_id,
                    self._sensor_stale_timeout_minutes,
                )
            self._sensor_valid = False
            self._schedule_failsafe_timer()

    def _handle_humidity_state(self, state) -> None:
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        try:
            self._current_humidity = round(float(state.state))
        except ValueError:
            pass

    def _schedule_failsafe_timer(self) -> None:
        if self._failsafe_unsub is not None or self._failsafe_active:
            return
        delay = timedelta(minutes=self._sensor_stale_timeout_minutes)
        self._failsafe_unsub = async_call_later(self.hass, delay, self._async_failsafe_triggered)

    def _cancel_failsafe_timer(self) -> None:
        if self._failsafe_unsub is not None:
            self._failsafe_unsub()
            self._failsafe_unsub = None

    @callback
    def _async_failsafe_triggered(self, _now: Any) -> None:
        self._failsafe_unsub = None
        if self._sensor_valid:
            return
        self._set_failsafe_active(True)
        _LOGGER.warning(
            "%s: sensor still invalid after %s minutes, closing heater output",
            self.entity_id,
            self._sensor_stale_timeout_minutes,
        )
        self.hass.async_create_task(self._async_set_heater(False))
        self._last_decision = "failsafe"
        self.async_write_ha_state()

    def _is_heater_on(self) -> bool:
        state = self.hass.states.get(self._heater_entity_id)
        return state is not None and state.state == STATE_ON

    async def _async_set_heater(self, turn_on: bool) -> None:
        if self._is_heater_on() == turn_on:
            return
        service = SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF
        await self.hass.services.async_call(
            HA_DOMAIN,
            service,
            {"entity_id": self._heater_entity_id},
            blocking=True,
            context=self._context,
        )

    def _set_window_open(self, open_: bool) -> None:
        """Publish the debounced window-open state for the companion binary sensor."""
        window_states = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            DATA_WINDOW_OPEN_STATES, {}
        )
        previous = window_states.get(self._subentry_id)
        self._window_open = open_
        window_states[self._subentry_id] = open_
        if previous != open_:
            async_dispatcher_send(self.hass, window_open_signal(self._subentry_id))

    def _is_any_window_open(self) -> bool:
        for entity_id in self._window_sensor_entity_ids:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_ON:
                return True
        return False

    def _handle_window_state(self) -> None:
        """Re-evaluate the debounced window-open state from current readings."""
        if self._is_any_window_open():
            if self._window_open or self._window_open_unsub is not None:
                return
            if self._window_open_delay:
                self._window_open_unsub = async_call_later(
                    self.hass, self._window_open_delay, self._async_window_open_confirmed
                )
            else:
                self._set_window_open(True)
        else:
            self._cancel_window_open_timer()
            if self._window_open:
                self._set_window_open(False)

    def _cancel_window_open_timer(self) -> None:
        if self._window_open_unsub is not None:
            self._window_open_unsub()
            self._window_open_unsub = None

    @callback
    def _async_window_open_confirmed(self, _now: Any) -> None:
        self._window_open_unsub = None
        if not self._is_any_window_open():
            return  # closed again before the delay elapsed
        self._set_window_open(True)
        self.hass.async_create_task(self._async_recontrol())

    def _schedule_active(self) -> bool:
        if not self._schedule_entity_id:
            return False
        state = self.hass.states.get(self._schedule_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        return state.state == STATE_ON

    @property
    def _effective_target_temperature(self) -> float | None:
        if self._attr_hvac_mode == HVACMode.OFF:
            return None
        if self._window_open:
            profile = self._profile_by_id(self._window_open_profile_id)
            return profile["temperature"] if profile is not None else self._eco_temp
        if self._attr_hvac_mode == HVACMode.AUTO:
            return self._comfort_temp if self._schedule_active() else self._eco_temp
        if self._attr_hvac_mode == HVACMode.HEAT:
            return self._attr_target_temperature
        return None

    def _min_cycle_elapsed(self) -> bool:
        if not self._min_cycle_duration:
            return True
        heater_state = self.hass.states.get(self._heater_entity_id)
        if heater_state is None or heater_state.last_changed is None:
            return True
        return dt_util.utcnow() - heater_state.last_changed >= self._min_cycle_duration

    async def _async_control_heating(self) -> None:
        """Re-evaluate the desired heater state. Idempotent, event-driven."""
        if self._attr_hvac_mode == HVACMode.OFF:
            await self._async_set_heater(False)
            self._last_decision = "off"
            return

        if self._failsafe_active or not self._sensor_valid:
            self._last_decision = "failsafe" if self._failsafe_active else "waiting_for_sensor"
            return

        target = self._effective_target_temperature
        if target is None or self._current_temp is None:
            self._last_decision = "no_target"
            return

        if not self._min_cycle_elapsed():
            self._last_decision = "min_cycle_wait"
            return

        too_cold = self._current_temp <= target - self._cold_tolerance
        too_hot = self._current_temp >= target + self._hot_tolerance

        if too_cold and not self._is_heater_on():
            await self._async_set_heater(True)
            self._last_decision = "heating_on"
        elif too_hot and self._is_heater_on():
            await self._async_set_heater(False)
            self._last_decision = "heating_off"
        else:
            self._last_decision = "hold"

    async def _async_recontrol(self) -> None:
        await self._async_control_heating()
        self.async_write_ha_state()

    # --- event listeners ----------------------------------------------------

    @callback
    def _async_temp_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        self._handle_temperature_state(event.data["new_state"])
        self.hass.async_create_task(self._async_recontrol())

    @callback
    def _async_humidity_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        self._handle_humidity_state(event.data["new_state"])
        self.async_write_ha_state()

    @callback
    def _async_heater_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @callback
    def _async_schedule_changed(self, event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self._async_recontrol())

    @callback
    def _async_window_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        was_open = self._window_open
        self._handle_window_state()
        if self._window_open != was_open:
            self.hass.async_create_task(self._async_recontrol())
        else:
            self.async_write_ha_state()
