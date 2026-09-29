"""Tests for the diagnostics download."""

from __future__ import annotations

from custom_components.climate_entity_builder.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .helpers import async_setup_base, make_hub_entry, profile_subentry, thermostat_subentry


async def test_diagnostics_separates_thermostats_and_profiles(hass) -> None:
    """A profile must not be reported as a thermostat with a missing entity."""
    await async_setup_base(hass, temperature=19.0)
    entry = make_hub_entry(
        subentries=[profile_subentry("Boost", 23.0), thermostat_subentry()]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert [t["title"] for t in result["thermostats"]] == ["Schlafzimmer"]
    assert result["thermostats"][0]["entity_id"] == "climate.schlafzimmer"
    assert [p["title"] for p in result["profiles"]] == ["Boost"]
    assert result["profiles"][0]["configuration"]["temperature"] == 23.0
