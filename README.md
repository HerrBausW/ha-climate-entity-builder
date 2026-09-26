# Room Thermostat

[![Test](https://github.com/HerrBausW/ha-room-thermostat/actions/workflows/test.yml/badge.svg)](https://github.com/HerrBausW/ha-room-thermostat/actions/workflows/test.yml)
[![Validate](https://github.com/HerrBausW/ha-room-thermostat/actions/workflows/validate.yml/badge.svg)](https://github.com/HerrBausW/ha-room-thermostat/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that builds a full virtual room thermostat
out of entities you already have: a temperature sensor, a switch (your heating
valve/relay), and optionally a humidity sensor and a `schedule.*` entity.

## Why

Home Assistant's built-in [`generic_thermostat`](https://www.home-assistant.io/integrations/generic_thermostat/)
covers the basic sensor+switch case, but it can't show the room's humidity on
the same `climate` entity, has no built-in failsafe for a dead sensor, and
needs YAML. Room Thermostat is configured entirely through the UI (Config
Flow + Subentries) and gives every room its own device with a single
`climate` entity that behaves like a native thermostat.

## Screenshots

*(placeholder — add screenshots of the device page and the climate card here)*

## Features

- One **Room Thermostat** hub integration, with one **sub-entry per room** —
  each room gets its own device in the Device Registry.
- `off` / `heat` / `auto` HVAC modes.
- `heat`: manual setpoint with configurable hysteresis (cold/hot tolerance).
- `auto`: uses an existing `schedule.*` entity — comfort temperature while the
  schedule is on, eco/setback temperature while it's off.
- Optional `comfort`/`eco` presets while in `heat` mode (hidden in `auto`,
  where the schedule is the single source of truth for the setpoint).
- Optional humidity sensor, shown as `current_humidity` on the same entity.
- Sensor failsafe: an `unavailable`/`unknown`/implausible reading closes the
  heater output after a configurable delay — but only after that delay, so a
  short glitch doesn't cut the heat.
- Fully event-driven (no polling).
- Restores HVAC mode and manual setpoint after a Home Assistant restart.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add `https://github.com/HerrBausW/ha-room-thermostat` as category
   **Integration**.
3. Install **Room Thermostat**, then restart Home Assistant.

### Manual

1. Copy `custom_components/room_thermostat` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. Settings → Devices & Services → Add Integration → **Room Thermostat**.
   This creates the hub (only one is needed/allowed).
2. On the integration's page, click **Add thermostat** and fill in the form:
   - Name (e.g. `Küche`)
   - Temperature sensor (`device_class: temperature`)
   - Heater output (a `switch.*` or `input_boolean.*`)
   - Optional: humidity sensor, schedule, min/max temperature, step size,
     cold/hot tolerance, minimum cycle duration, comfort/eco temperature,
     failsafe delay and plausibility bounds.
3. Repeat step 2 for every room. Each one becomes its own device with a
   `climate.*` entity.
4. To change a thermostat's configuration later, or to remove it, use the
   device's own menu (**Reconfigure** / **Delete**) — no YAML involved.

## Modes

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

Create a schedule like `schedule.heizung_kueche` in Settings → Automations &
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

## Known limitations

- `auto` mode only supports a single on/off schedule with a comfort and an
  eco temperature — no per-time-slot temperatures, multiple schedules,
  weekdays, holidays, presence or window sensors yet (see Roadmap).
- Manually setting a temperature while in `auto` mode is not supported by
  design, to avoid two conflicting ways to pick the setpoint.
- The heater output must already exist as a `switch.*` or `input_boolean.*`
  entity; multiple actuators per room are not yet supported.
- The entity id of a newly added thermostat is derived from its name (e.g.
  `climate.thermostat_kueche`), not from any previous entity — see Migration.

## Example configuration (private test setup)

| Room       | Temperature                          | Humidity                               | Heater                            |
|------------|---------------------------------------|------------------------------------------|------------------------------------|
| Schlafzimmer | `sensor.schlafzimmer_temperatur`    | `sensor.schlafzimmer_luftfeuchtigkeit`  | `switch.schlafzimmer_heizventil`  |
| Küche      | `sensor.kuche_temperatur`             | `sensor.kuche_luftfeuchtigkeit`          | `switch.kuche_heizventil`         |
| Gäste-WC   | `sensor.gaste_wc_temperatur`          | `sensor.gaste_wc_luftfeuchtigkeit`       | `switch.gaste_wc_heizventil`      |

Suggested values matching a typical `generic_thermostat` migration:
`min_temp: 5`, `max_temp: 30.5`, `cold_tolerance: 0.2`, `hot_tolerance: 0.2`,
`target_temp_step: 0.5`, failsafe delay `15` minutes, plausibility `5`–`40 °C`.

## Migration from `generic_thermostat`

Home Assistant won't let two entities share an entity id, so a direct
takeover of e.g. `climate.schlafzimmer` isn't possible while the old entity
still exists. Recommended path, one room at a time:

1. Keep the existing `generic_thermostat` and its failsafe automation
   running for now.
2. Add the new thermostat here for the **same room** (it will get an entity
   id like `climate.thermostat_schlafzimmer`).
3. Verify it for a few days: heating behaviour, hysteresis, humidity, and
   (if used) the schedule.
4. Go to Settings → Devices & Services → Entities, disable/rename the old
   `generic_thermostat` entity (e.g. to `climate.schlafzimmer_old`), then
   rename the new entity's id to `climate.schlafzimmer` from its entity
   settings dialog. Dashboards and automations referencing the old id keep
   working.
5. Only now remove the old `generic_thermostat` YAML/config entry and its
   failsafe automation.

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

Not in the MVP, but the architecture leaves room for: window/door contacts
pausing heating, presence & vacation modes, a timed boost preset, frost
protection, multiple heater actuators per room, cooling, external temperature
limiting, valve run-on, per-time-slot schedules with weekdays, and dedicated
diagnostic/statistics entities.

## License

[MIT](LICENSE)
