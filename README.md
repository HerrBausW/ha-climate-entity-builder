# Climate Entity Builder

[![Test](https://github.com/HerrBausW/ha-climate-entity-builder/actions/workflows/test.yml/badge.svg)](https://github.com/HerrBausW/ha-climate-entity-builder/actions/workflows/test.yml)
[![Validate](https://github.com/HerrBausW/ha-climate-entity-builder/actions/workflows/validate.yml/badge.svg)](https://github.com/HerrBausW/ha-climate-entity-builder/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Turn any temperature sensor and switch into a full-featured virtual thermostat — no YAML, entirely through the Home Assistant UI.**

<p align="center">
  <img src="https://raw.githubusercontent.com/HerrBausW/ha-climate-entity-builder/main/images/integration-overview.png" width="720" alt="Climate Entity Builder integration page: one hub with a device per room, each a Virtual Room Thermostat with 3 entities">
</p>

## Contents

- [Why](#why)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Setup](#setup)
- [Modes](#modes)
- [Hysteresis](#hysteresis)
- [Failsafe](#failsafe)
- [Window contacts](#window-contacts)
- [Custom preset profiles](#custom-preset-profiles)
- [Companion sensors](#companion-sensors)
- [Known limitations](#known-limitations)
- [Example configuration](#example-configuration)
- [Migration from `generic_thermostat`](#migration-from-generic_thermostat)
- [Development / tests](#development--tests)
- [Roadmap](#roadmap)

## Why

Home Assistant's built-in [`generic_thermostat`](https://www.home-assistant.io/integrations/generic_thermostat/)
covers the basic sensor+switch case, but it can't show the room's humidity on
the same `climate` entity, has no built-in failsafe for a dead sensor, and
needs YAML. **Climate Entity Builder** is configured entirely through the UI
(Config Flow + Subentries) and gives every room its own device with a single
`climate` entity that behaves like a native thermostat — plus a couple of
companion sensors, so it fits right into an existing maintenance dashboard.

## Features

- One or more **Climate Entity Builder** hubs, each with one **sub-entry per
  room** — every room gets its own device in the Device Registry, named
  exactly what you type. Multiple hubs are useful for giving different
  floors/areas their own independent set of custom preset profiles.
- `off` / `heat` / `auto` HVAC modes, with configurable hysteresis in `heat`
  and a schedule-driven setpoint in `auto`.
- Optional humidity sensor, shown as `current_humidity` on the same entity.
- Optional **offsets** for the temperature and humidity sensor, to correct a
  sensor that reads too high or too low.
- `comfort`/`eco` presets plus any number of your own **custom preset
  profiles** (name + temperature) while in `heat` mode (hidden in `auto`,
  where the schedule is the single source of truth for the setpoint).
- Sensor failsafe with a configurable grace period and plausibility bounds —
  a brief glitch never cuts the heat, a genuinely dead sensor does.
- Optional window/door contacts pause heating and switch to a dedicated
  **window-open temperature** — regulated, not just switched fully off.
- Optional **area** assignment when adding a thermostat.
- Companion `binary_sensor` entities per thermostat for maintenance
  dashboards: **heating activity**, **failsafe**, and (if configured)
  **window pause active**.
- The entity id is derived directly from the name you enter (`Bedroom` →
  `climate.bedroom`), matching how people already name a manual thermostat.
- Fully event-driven (no polling), restores HVAC mode and setpoint across a
  Home Assistant restart.
- English and German UI, and a downloadable diagnostics report.

## Requirements

Home Assistant **2025.9 or newer** (this integration relies on
[config subentries](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/#config-subentries),
introduced in HA 2025.7).

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add `https://github.com/HerrBausW/ha-climate-entity-builder` as category
   **Integration**.
3. Install **Climate Entity Builder**, then restart Home Assistant.

### Manual

1. Copy `custom_components/climate_entity_builder` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. Settings → Devices & Services → Add Integration → **Climate Entity
   Builder**. Give the hub a name — one hub is enough for most setups, but
   you can add more (e.g. one per floor) if you want separate sets of
   custom preset profiles (see [below](#custom-preset-profiles)).
2. On the hub's page, click **Add thermostat** and fill in the form. Fields
   that aren't self-explanatory have a short explanation underneath. Required
   are only the name, the temperature sensor and the heater output;
   everything else has a sensible default:

   - **Name** (e.g. `Kitchen`)
   - **Area** (optional) — assigned to the device once, right now; a later
     manual reassignment on the device's own page always takes precedence
     over changing this field again
   - **Temperature sensor** (`device_class: temperature`) with an optional
     **temperature offset** (default 0 °C) to correct a sensor that reads
     too warm or too cold. The offset applies to what's shown and to
     regulation; the failsafe plausibility bounds still judge the raw
     reading, so an offset can never hide a dead sensor.
   - **Heater output** (a `switch.*` or `input_boolean.*`)
   - **Humidity sensor** (optional) with its own **humidity offset**
     (default 0 %, result kept within 0–100 %)
   - **Minimum / maximum temperature** that can be set
   - Collapsible groups:
     - *Hysteresis & switch cycling* — setpoint step size, cold/hot
       tolerance, optional minimum switch cycle duration
     - *Window pause* — window/door sensors, an optional open delay and the
       window-open temperature
     - *Presets & schedule* — optional schedule for `auto` mode, comfort and
       eco temperature
   - **Failsafe** — delay after an invalid reading and the plausibility
     bounds
3. Repeat step 2 for every room. Each one becomes its own device with a
   `climate.*` entity.
4. To change a thermostat's configuration later, or to remove it, use the
   device's own menu (**Reconfigure** / **Delete**) — no YAML involved.

## Modes

The resulting `climate` entity behaves like a native thermostat, including
Home Assistant's standard dial card:

<p align="center">
  <img src="https://raw.githubusercontent.com/HerrBausW/ha-climate-entity-builder/main/images/climate-card.png" width="360" alt="Native Home Assistant climate card for a Climate Entity Builder thermostat, showing current temperature, humidity, setpoint dial and HVAC mode">
</p>

- **off** — heater output is always held off.
- **heat** — you set `target_temperature` manually; the heater is switched
  by hysteresis around that value (see below).
- **auto** — only available once a schedule entity is configured. While the
  schedule is `on`, the *comfort* temperature is the effective target; while
  it's `off`, the *eco* temperature is used. The effective target is shown as
  the entity's `target_temperature` and additionally as the
  `effective_target_temperature` attribute. Manually setting a temperature
  while in `auto` is rejected — switch to `heat`, or edit the comfort/eco
  values, instead.

### Schedule example

Create a schedule like `schedule.kitchen_heating` in Settings → Automations &
Scenes → Schedules (e.g. weekdays 06:00–22:00), then select it as this
thermostat's schedule. Whenever that schedule is active, `auto` mode uses the
comfort temperature; otherwise the eco/setback temperature.

## Hysteresis

With a setpoint of 20.0 °C, `cold_tolerance = 0.2` and `hot_tolerance = 0.2`:

- heater turns **on** at ≤ 19.8 °C
- heater turns **off** at ≥ 20.2 °C
- between those two points, the existing switch state is left alone.

## Failsafe

If the temperature sensor becomes `unavailable`, `unknown`, non-numeric, or
falls outside the configured plausibility bounds (default 5–40 °C), the
integration waits for the configured delay (default 15 minutes) before
forcing the heater output off. A brief glitch that clears within the delay
never touches the output. Once a valid reading arrives, normal control
resumes immediately and the failsafe attribute clears.

The plausibility bounds are checked against the sensor's **raw** reading,
before the temperature offset is applied — an offset can never move a bad
reading back into range and hide a dead sensor.

## Window contacts

Optionally select one or more `binary_sensor.*` window/door contacts and set
a **window-open temperature**. While any of them is open (after an optional
delay, to ignore a quick opening for airing out the room), the thermostat
regulates against that temperature instead of the normal setpoint — it
doesn't just switch fully off, so the room still gets a minimal amount of
heat. This only applies while the thermostat is in `heat`/`auto`; if it's
`off`, it stays `off` regardless of any window.

While paused, the preset chip on the climate card (*Voreinstellung* in a
German UI) shows **Window open** in place of the normal comfort/eco/none
value. It can't be selected manually. Your actual
setpoint and preset underneath are untouched and reassert themselves the
moment the window closes — nothing to reset manually.

## Custom preset profiles

Beyond the built-in `comfort`/`eco` presets, click **Add profile** on a
hub's device page to define your own — a name and a temperature (e.g.
`Boost: 23°C`, `Vacation: 15°C`). Every profile is offered as an extra
preset, identically, on **every thermostat under that same hub** — there's
no per-room override. If you want different profiles for different areas
(e.g. a floor with its own vacation temperature), set up a separate hub for
that area instead; a thermostat only ever sees the profiles of its own
hub. Profiles are only offered in `heat` mode, same as `comfort`/`eco`.

A profile's name can't reuse one of the built-in preset identifiers
(`none`, `comfort`, `eco`, `window_open` — case-insensitive).

A profile can optionally have its own icon. It's shown on the thermostat
entity itself (sidebar, history graph, more-info header) while that profile
is the active preset — not in the preset picker's own dropdown row, which
can't show a custom icon for a dynamically-named preset like this.

## Companion sensors

Every thermostat device carries read-only `binary_sensor` entities alongside
the `climate` entity, so it slots into a maintenance dashboard the same way a
wall-mounted thermostat's status entities would:

| Name (EN / DE) | Reflects | Device class |
|---|---|---|
| Heating activity / Heizaktivität | the real heater output (`switch`/`input_boolean`), not the HVAC mode | — |
| Failsafe / Failsafe | whether this thermostat's failsafe is currently engaged | `problem` |
| Window pause active / Fensterpause aktiv | whether heating is currently paused for an open window, i.e. after the configured delay has elapsed — not a live mirror of the raw contact sensor (only created if window sensors are configured) | `window` |

Their entity ids are `binary_sensor.<room>_<name>`, built from the name in
the language Home Assistant was set to *when the thermostat was created*
(e.g. `binary_sensor.kitchen_heizaktivitat` on a German setup) — check the
device page for the exact id.

## Known limitations

- `auto` mode only supports a single on/off schedule with a comfort and an
  eco temperature — no per-time-slot temperatures, multiple schedules,
  weekdays, holidays or presence yet (see Roadmap).
- Manually setting a temperature while in `auto` mode is not supported by
  design, to avoid two conflicting ways to pick the setpoint.
- The heater output must already exist as a `switch.*` or `input_boolean.*`
  entity; multiple actuators per room are not yet supported.
- A custom profile has one temperature for every thermostat under its hub;
  there's no per-room override. Use a separate hub if an area needs its own.
- If a profile is renamed or deleted while it's a thermostat's active
  preset, that thermostat falls back to `none` (the hub reloads right after
  such a change).
- The window-open temperature is set per thermostat (not shared through a
  profile).
- A custom profile's icon can't be shown inside the preset picker's own
  dropdown (a Home Assistant limitation for dynamically named presets); it
  appears on the entity itself while that profile is active.

## Example configuration

| Room        | Temperature                       | Humidity                           | Heater                       |
|-------------|-------------------------------------|---------------------------------------|---------------------------------|
| Bedroom     | `sensor.bedroom_temperature`       | `sensor.bedroom_humidity`          | `switch.bedroom_heating_valve` |
| Kitchen     | `sensor.kitchen_temperature`       | `sensor.kitchen_humidity`          | `switch.kitchen_heating_valve` |
| Guest toilet| `sensor.guest_toilet_temperature`  | `sensor.guest_toilet_humidity`     | `switch.guest_toilet_heating_valve` |

Reasonable starting values for underfloor/radiator heating with a slow
response: `min_temp: 5`, `max_temp: 30.5`, `cold_tolerance: 0.2`,
`hot_tolerance: 0.2`, `target_temp_step: 0.5`, failsafe delay `15` minutes,
plausibility `5`–`40 °C`.

## Migration from `generic_thermostat`

If you're coming from Home Assistant's built-in `generic_thermostat` (a very
common way to build a sensor+switch thermostat before this integration
existed): the entity id here is derived directly from the name you enter, so
if you name the new thermostat exactly like the room (e.g. `Bedroom`) while
the old `generic_thermostat` entity `climate.bedroom` still exists, Home
Assistant can't give both the same id and will suffix the new one (e.g.
`climate.bedroom_2`). Recommended path, one room at a time:

1. Keep the existing `generic_thermostat` and its failsafe automation
   running for now.
2. Add the new thermostat here for the **same room**, giving it a
   temporarily distinct name (e.g. `Bedroom New`) so it doesn't collide with
   the still-existing `climate.bedroom`.
3. Verify it for a few days: heating behaviour, hysteresis, humidity, and
   (if used) the schedule.
4. Remove the old `generic_thermostat` YAML/config entry and its failsafe
   automation, which frees up `climate.bedroom`.
5. Rename the new thermostat back to `Bedroom` via **Reconfigure**, then
   rename its entity id to `climate.bedroom` from its entity settings
   dialog. Dashboards and automations referencing the old id keep working.

## Development / tests

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements_test.txt
pytest tests
```

CI runs the test suite plus [Hassfest](https://developers.home-assistant.io/docs/creating_integration_manifest/#hassfest)
and [HACS validation](https://hacs.xyz/docs/publish/action/) on every push
and pull request.

## Roadmap

Not in the MVP, but the architecture leaves room for: a *timed* boost
preset (auto-reverting after a duration), multiple heater actuators per
room, cooling, external temperature limiting, valve run-on, per-time-slot
schedules with weekdays, and dedicated diagnostic/statistics entities.

## License

[MIT](LICENSE)
