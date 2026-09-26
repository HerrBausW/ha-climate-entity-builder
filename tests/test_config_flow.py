"""Tests for the Room Thermostat config & subentry flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.room_thermostat.const import (
    CONF_HEATER,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_NAME,
    DOMAIN,
    SUBENTRY_TYPE_THERMOSTAT,
)

from .helpers import make_hub_entry, thermostat_data, thermostat_subentry


async def test_hub_config_flow_creates_single_entry(hass) -> None:
    """The hub config flow (item 1) creates exactly one entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Room Thermostat"

    # A second attempt aborts: only a single hub instance is supported.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_add_thermostat_subentry_success(hass) -> None:
    """Successful setup of a thermostat via the subentry flow (item 2)."""
    entry = make_hub_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_THERMOSTAT), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], thermostat_data()
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Schlafzimmer"

    assert len(entry.subentries) == 1
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_NAME] == "Schlafzimmer"


async def test_add_thermostat_duplicate_name_rejected(hass) -> None:
    """Two thermostats may not share a name."""
    entry = make_hub_entry(subentries=[thermostat_subentry(name="Schlafzimmer")])
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_THERMOSTAT), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], thermostat_data(name="Schlafzimmer")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_NAME] == "name_exists"


async def test_add_thermostat_invalid_temperature_range(hass) -> None:
    """min_temp must be lower than max_temp."""
    entry = make_hub_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_THERMOSTAT), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        thermostat_data(**{CONF_MIN_TEMP: 25.0, CONF_MAX_TEMP: 20.0}),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_MAX_TEMP] == "min_max_invalid"


async def test_reconfigure_thermostat_changes_entities(hass) -> None:
    """Changing the sensor/heater selection via reconfigure (item 13)."""
    entry = make_hub_entry(subentries=[thermostat_subentry()])
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_THERMOSTAT),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM

    new_data = thermostat_data(
        **{CONF_HEATER: "switch.kuche_heizventil", CONF_NAME: "Schlafzimmer"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], new_data
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    updated = entry.subentries[subentry.subentry_id]
    assert updated.data[CONF_HEATER] == "switch.kuche_heizventil"


async def test_remove_thermostat_subentry(hass) -> None:
    """Removing a thermostat subentry (item 12) drops it from the entry."""
    entry = make_hub_entry(subentries=[thermostat_subentry()])
    entry.add_to_hass(hass)
    subentry_id = next(iter(entry.subentries))

    hass.config_entries.async_remove_subentry(entry, subentry_id)

    assert subentry_id not in entry.subentries
