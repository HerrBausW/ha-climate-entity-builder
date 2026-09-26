"""Shared fixtures for Room Thermostat tests."""

import pytest

from homeassistant.setup import async_setup_component

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ discoverable in every test."""
    yield


@pytest.fixture(autouse=True)
async def setup_homeassistant(hass):
    """The heater is toggled via the generic homeassistant.turn_on/turn_off
    services, which live in the "homeassistant" integration and are not
    loaded automatically by the bare `hass` test fixture."""
    assert await async_setup_component(hass, "homeassistant", {})
