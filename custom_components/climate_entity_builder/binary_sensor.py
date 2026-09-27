"""Binary sensor platform for Climate Entity Builder."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_HEATER,
    CONF_NAME,
    CONF_WINDOW_SENSORS,
    DATA_FAILSAFE_STATES,
    DATA_WINDOW_OPEN_STATES,
    DOMAIN,
    MANUFACTURER,
    SUBENTRY_TYPE_THERMOSTAT,
    failsafe_signal,
    window_open_signal,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up status binary sensors for every thermostat subentry."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_THERMOSTAT:
            continue
        entities: list[RoomThermostatBinarySensor] = [
            RoomThermostatHeatingActivity(subentry),
            RoomThermostatFailsafe(subentry),
        ]
        if subentry.data.get(CONF_WINDOW_SENSORS):
            entities.append(RoomThermostatWindowOpen(subentry))
        async_add_entities(entities, config_subentry_id=subentry_id)


class RoomThermostatBinarySensor(BinarySensorEntity):
    """Base class for entities attached to one virtual thermostat device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, subentry: ConfigSubentry) -> None:
        self._subentry_id = subentry.subentry_id
        name = subentry.data[CONF_NAME]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Virtual Room Thermostat",
        )


class RoomThermostatHeatingActivity(RoomThermostatBinarySensor):
    """Expose the actual heater output as a read-only binary sensor."""

    _attr_translation_key = "heating_activity"
    _attr_icon = "mdi:heating-coil"

    def __init__(self, subentry: ConfigSubentry) -> None:
        super().__init__(subentry)
        self._attr_unique_id = f"{subentry.subentry_id}_heating_activity"
        self._heater_entity_id: str = subentry.data[CONF_HEATER]

    async def async_added_to_hass(self) -> None:
        """Track the configured heater output."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._heater_entity_id],
                self._async_heater_changed,
            )
        )

    @property
    def is_on(self) -> bool:
        """Return whether the physical heater output is active."""
        state = self.hass.states.get(self._heater_entity_id)
        return state is not None and state.state == STATE_ON

    @property
    def available(self) -> bool:
        """Return whether the physical heater output has a valid state."""
        state = self.hass.states.get(self._heater_entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    @callback
    def _async_heater_changed(self, event: Event[EventStateChangedData]) -> None:
        """Update the entity when the heater output changes."""
        self.async_write_ha_state()


class RoomThermostatFailsafe(RoomThermostatBinarySensor):
    """Expose the thermostat's internal failsafe as a problem sensor."""

    _attr_translation_key = "failsafe"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, subentry: ConfigSubentry) -> None:
        super().__init__(subentry)
        self._attr_unique_id = f"{subentry.subentry_id}_failsafe"

    async def async_added_to_hass(self) -> None:
        """Listen for failsafe state changes from the climate entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                failsafe_signal(self._subentry_id),
                self._async_failsafe_changed,
            )
        )

    @property
    def is_on(self) -> bool:
        """Return whether the thermostat failsafe is active."""
        return bool(
            self.hass.data.get(DOMAIN, {})
            .get(DATA_FAILSAFE_STATES, {})
            .get(self._subentry_id, False)
        )

    @callback
    def _async_failsafe_changed(self) -> None:
        """Update the entity when the climate entity publishes a new state."""
        self.async_write_ha_state()


class RoomThermostatWindowOpen(RoomThermostatBinarySensor):
    """Expose the thermostat's debounced window-open state."""

    _attr_translation_key = "window_open"
    _attr_device_class = BinarySensorDeviceClass.WINDOW

    def __init__(self, subentry: ConfigSubentry) -> None:
        super().__init__(subentry)
        self._attr_unique_id = f"{subentry.subentry_id}_window_open"

    async def async_added_to_hass(self) -> None:
        """Listen for window-open state changes from the climate entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                window_open_signal(self._subentry_id),
                self._async_window_open_changed,
            )
        )

    @property
    def is_on(self) -> bool:
        """Return whether this thermostat currently has a window open."""
        return bool(
            self.hass.data.get(DOMAIN, {})
            .get(DATA_WINDOW_OPEN_STATES, {})
            .get(self._subentry_id, False)
        )

    @callback
    def _async_window_open_changed(self) -> None:
        """Update the entity when the climate entity publishes a new state."""
        self.async_write_ha_state()
