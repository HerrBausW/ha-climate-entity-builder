"""Tests for the Climate Entity Builder config & subentry flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.climate_entity_builder.config_flow import _thermostat_data_schema
from custom_components.climate_entity_builder.const import (
    CONF_HEATER,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_NAME,
    CONF_WINDOW_SENSORS,
    DOMAIN,
    SUBENTRY_TYPE_THERMOSTAT,
)

from .helpers import make_hub_entry, thermostat_data, thermostat_subentry


def _marker_default(schema, key: str):
    """Return the resolved default for a vol.Schema key marker."""
    marker = next(k for k in schema.schema if str(k) == key)
    return marker.default()


async def test_hub_config_flow_creates_entry(hass) -> None:
    """The hub config flow (item 1) creates an entry, defaulting its name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Climate Entity Builder"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Climate Entity Builder"

    # A second, independently-named hub is allowed (see test_profiles.py for
    # the multi-hub / per-hub-profiles coverage).
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Zweiter Hub"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zweiter Hub"


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


def test_window_sensors_default_is_never_none() -> None:
    """A previously-saved None must not reach the multi-select as its default.

    A stored `window_sensors: None` (present key, not missing) is what broke
    this one field's rendering in Reconfigure for an existing thermostat,
    even though a merely-absent key correctly falls back to []. Guard both.
    """
    assert _marker_default(_thermostat_data_schema({}), CONF_WINDOW_SENSORS) == []
    assert (
        _marker_default(
            _thermostat_data_schema({CONF_WINDOW_SENSORS: None}), CONF_WINDOW_SENSORS
        )
        == []
    )
    assert (
        _marker_default(
            _thermostat_data_schema({CONF_WINDOW_SENSORS: ["binary_sensor.x"]}),
            CONF_WINDOW_SENSORS,
        )
        == ["binary_sensor.x"]
    )


async def test_reconfigure_self_heals_stale_none_window_sensors(hass) -> None:
    """A thermostat with a legacy `window_sensors: None` must self-heal on save.

    Mirrors the exact live bug: a thermostat saved under an older schema
    version had a literal None stored (not a missing key) for this field.
    The frontend's own selector can no longer submit None going forward
    (its validator no longer accepts it), so the only way stale None data
    exists is data persisted before this fix - reproduced here directly on
    the stored subentry rather than through the flow's own validation.
    """
    entry = make_hub_entry(
        subentries=[thermostat_subentry(**{CONF_WINDOW_SENSORS: None})]
    )
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_WINDOW_SENSORS] is None

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_THERMOSTAT),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert _marker_default(result["data_schema"], CONF_WINDOW_SENSORS) == []

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], thermostat_data()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    updated = entry.subentries[subentry.subentry_id]
    assert updated.data[CONF_WINDOW_SENSORS] == []


async def test_remove_thermostat_subentry(hass) -> None:
    """Removing a thermostat subentry (item 12) drops it from the entry."""
    entry = make_hub_entry(subentries=[thermostat_subentry()])
    entry.add_to_hass(hass)
    subentry_id = next(iter(entry.subentries))

    hass.config_entries.async_remove_subentry(entry, subentry_id)

    assert subentry_id not in entry.subentries
