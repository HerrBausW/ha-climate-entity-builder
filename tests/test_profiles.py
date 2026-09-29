"""Tests for custom preset profiles, scoped per hub."""

from __future__ import annotations

from homeassistant.components.climate import ATTR_PRESET_MODE, HVACMode
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import State
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.climate_entity_builder.const import (
    CONF_NAME,
    CONF_PROFILE_TEMPERATURE,
    SUBENTRY_TYPE_PROFILE,
)

from .helpers import async_setup_base, make_hub_entry, profile_subentry, thermostat_subentry

CLIMATE_ENTITY_ID = "climate.schlafzimmer"


async def _set_hvac_mode(hass, entity_id: str, hvac_mode: str) -> None:
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": hvac_mode},
        blocking=True,
    )


async def test_add_profile_subentry_success(hass) -> None:
    """Adding a profile via the subentry flow stores name + temperature."""
    entry = make_hub_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PROFILE), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Boost", CONF_PROFILE_TEMPERATURE: 23.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boost"

    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_NAME] == "Boost"
    assert subentry.data[CONF_PROFILE_TEMPERATURE] == 23.0


async def test_add_profile_duplicate_name_rejected(hass) -> None:
    """Two profiles under the same hub may not share a name."""
    entry = make_hub_entry(subentries=[profile_subentry("Boost", 23.0)])
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PROFILE), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Boost", CONF_PROFILE_TEMPERATURE: 19.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_NAME] == "name_exists"


async def test_add_profile_reserved_name_rejected(hass) -> None:
    """A profile can't shadow one of the built-in preset identifiers."""
    entry = make_hub_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PROFILE), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Eco", CONF_PROFILE_TEMPERATURE: 19.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_NAME] == "name_reserved"


async def test_reconfigure_profile_updates_temperature(hass) -> None:
    """Editing a profile updates its stored temperature."""
    entry = make_hub_entry(subentries=[profile_subentry("Boost", 23.0)])
    entry.add_to_hass(hass)
    subentry = next(iter(entry.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PROFILE),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Boost", CONF_PROFILE_TEMPERATURE: 24.5}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry.subentry_id].data[CONF_PROFILE_TEMPERATURE] == 24.5


async def test_profile_selectable_only_in_heat_mode(hass) -> None:
    """A profile is offered as a preset in heat mode, but not off/auto."""
    await async_setup_base(hass, temperature=19.0)
    entry = make_hub_entry(
        subentries=[profile_subentry("Boost", 23.0), thermostat_subentry()]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert "Boost" not in state.attributes["preset_modes"]

    await _set_hvac_mode(hass, CLIMATE_ENTITY_ID, HVACMode.HEAT)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert "Boost" in state.attributes["preset_modes"]


async def test_selecting_profile_sets_its_temperature(hass) -> None:
    """Selecting a profile preset applies its configured temperature."""
    await async_setup_base(hass, temperature=19.0)
    entry = make_hub_entry(
        subentries=[profile_subentry("Boost", 23.0), thermostat_subentry()]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _set_hvac_mode(hass, CLIMATE_ENTITY_ID, HVACMode.HEAT)

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": CLIMATE_ENTITY_ID, ATTR_PRESET_MODE: "Boost"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == "Boost"
    assert state.attributes[ATTR_TEMPERATURE] == 23.0


async def test_profile_preset_survives_restart(hass) -> None:
    """A selected profile preset is restored across a Home Assistant restart."""
    mock_restore_cache(
        hass,
        [
            State(
                CLIMATE_ENTITY_ID,
                HVACMode.HEAT,
                {ATTR_TEMPERATURE: 23.0, ATTR_PRESET_MODE: "Boost"},
            )
        ],
    )
    await async_setup_base(hass, temperature=19.0)
    entry = make_hub_entry(
        subentries=[profile_subentry("Boost", 23.0), thermostat_subentry()]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == "Boost"
    assert state.attributes[ATTR_TEMPERATURE] == 23.0


async def test_restart_drops_a_since_removed_profile(hass) -> None:
    """A restored preset that no longer exists as a profile falls back to none."""
    mock_restore_cache(
        hass,
        [
            State(
                CLIMATE_ENTITY_ID,
                HVACMode.HEAT,
                {ATTR_TEMPERATURE: 23.0, ATTR_PRESET_MODE: "Boost"},
            )
        ],
    )
    await async_setup_base(hass, temperature=19.0)
    # No "Boost" profile this time - it was removed/renamed while HA was off.
    entry = make_hub_entry(subentries=[thermostat_subentry()])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE_ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == "none"


async def test_thermostat_only_sees_its_own_hubs_profiles(hass) -> None:
    """Hub isolation: a thermostat under Hub A must not see Hub B's profiles."""
    await async_setup_base(hass, temperature=19.0)

    hub_a = make_hub_entry(
        subentries=[profile_subentry("Boost", 23.0), thermostat_subentry()]
    )
    hub_a.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_a.entry_id)

    hub_b = make_hub_entry(
        subentries=[
            profile_subentry("Urlaub", 15.0),
            thermostat_subentry(name="Kueche"),
        ]
    )
    hub_b.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_b.entry_id)
    await hass.async_block_till_done()

    await _set_hvac_mode(hass, CLIMATE_ENTITY_ID, HVACMode.HEAT)
    await _set_hvac_mode(hass, "climate.kueche", HVACMode.HEAT)
    await hass.async_block_till_done()

    schlafzimmer = hass.states.get(CLIMATE_ENTITY_ID)
    kueche = hass.states.get("climate.kueche")

    assert "Boost" in schlafzimmer.attributes["preset_modes"]
    assert "Urlaub" not in schlafzimmer.attributes["preset_modes"]

    assert "Urlaub" in kueche.attributes["preset_modes"]
    assert "Boost" not in kueche.attributes["preset_modes"]
