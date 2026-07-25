# Evaporative Control Modes

## Goal

Represent an evaporative-only MagIQtouch installation accurately in Home
Assistant while preserving existing support for heating and combined systems.

The physical controller supports:

- evaporative cooling controlled by a target temperature;
- evaporative cooling controlled by a manual fan speed from 1 to 10;
- air-only ventilation using outside air at fan speeds from 1 to 10; and
- system off.

An evaporative-only installation must never advertise heating.

## Home Assistant Model

Use one climate entity for the physical MagIQtouch system.

| Home Assistant state | Controller state | Control |
| --- | --- | --- |
| Off | `systemOn=false` | None |
| Cool, temperature | `runningMode=COOL`, `control_mode=TEMP` | Target temperature |
| Cool, manual | `runningMode=COOL`, `control_mode=FAN` | Fan speed 1-10 |
| Fan only | `runningMode=COOLER_FAN` | Outside-air fan speed 1-10 |

The entity advertises `off`, `cool`, and `fan_only` when only an evaporative
cooler is installed. It advertises `heat` only when heater equipment is
reported by the controller.

## Command Behaviour

Commands must update the complete intended controller state before sending the
full-state WebSocket payload:

1. Setting a target temperature while cooling sets `runningMode=COOL`,
   `control_mode=TEMP`, the requested setpoint, and the required running state
   in one command.
2. Selecting fan speed 1-10 while cooling sets `runningMode=COOL`,
   `control_mode=FAN`, the requested speed, and the required running state in
   one command.
3. Selecting fan speed 1-10 while in air-only mode retains
   `runningMode=COOLER_FAN` and updates the cooler fan speed.
4. Selecting `fan_only` on an evaporative-only system explicitly selects
   `COOLER_FAN`; it must not depend on heater state.
5. Unsupported heating requests are not advertised and are not routed to
   heater commands.

Atomic state changes avoid sending an intermediate full-state command that
could briefly select the wrong control mode or overwrite a physical-controller
change.

## Compatibility

Heating-only and combined installations keep their existing modes. Equipment
routing remains capability-driven so cooler commands affect cooler records and
heater commands affect heater records.

Existing preset names remain available for compatibility, but the normal
controls are HVAC mode, target temperature, and fan mode.

## Testing

Regression tests will cover:

- evaporative-only advertised HVAC modes;
- selecting fan-only from cooling;
- setting a target temperature from manual cooling;
- selecting a numeric speed from temperature-controlled cooling;
- changing speed while remaining in air-only mode;
- absence of heating commands and heating mode for evaporative-only systems;
- preservation of existing heater routing tests.

The full test suite, Ruff checks, JSON/YAML validation, and repository
validation workflow will run before publishing.
