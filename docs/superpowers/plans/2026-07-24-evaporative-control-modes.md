# Evaporative Control Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an evaporative-only MagIQtouch climate entity reliably control target-temperature cooling, fixed-speed cooling, and fixed-speed outside-air ventilation without exposing heating.

**Architecture:** Keep the existing single climate entity and capability-driven equipment discovery. Add optional target values to the driver's mode-changing methods so each full-state WebSocket command contains the requested running mode, control mode, and temperature or speed atomically; then route Home Assistant controls to those methods according to the current HVAC mode.

**Tech Stack:** Python 3.11, Home Assistant `ClimateEntity`, asyncio, pytest, pytest-asyncio, Ruff, HACS validation, hassfest.

## Global Constraints

- An evaporative-only installation advertises only `off`, `cool`, and `fan_only`.
- `COOL` plus `control_mode=TEMP` uses the target temperature.
- `COOL` plus `control_mode=FAN` uses fan speed 1-10.
- `COOLER_FAN` is outside-air-only ventilation and supports fan speed 1-10.
- Heating and combined installations retain their existing capability-driven modes.
- Each user action sends one complete intended controller state because MagIQtouch commands overwrite full state.

---

## File Structure

- `custom_components/magiqtouch/magiqtouch.py`: owns atomic controller-state mutations and WebSocket command submission.
- `custom_components/magiqtouch/climate.py`: maps Home Assistant climate controls to installed equipment and driver operations.
- `tests/test_magiqtouch.py`: proves atomic cooler state mutations before a command is sent.
- `tests/test_climate.py`: proves the Home Assistant mode and control transitions.
- `Readme.md`: documents the controls presented to evaporative-only users.

### Task 1: Atomic Evaporative Driver Commands

**Files:**
- Modify: `custom_components/magiqtouch/magiqtouch.py:643-738`
- Test: `tests/test_magiqtouch.py`

**Interfaces:**
- Consumes: `UnitDetails.control_mode`, `UnitDetails.set_temp`, `UnitDetails.fan_speed`, `RemoteStatus.runningMode`, and `RemoteStatus.systemOn`.
- Produces: `set_cooling_by_temperature(zone=ZONE_NONE, temperature=None)`, `set_cooling_by_speed(zone=ZONE_NONE, speed=None)`, equivalent optional-value heater methods for compatibility, and zone-aware `set_current_speed(speed, zone=ZONE_NONE)`.

- [ ] **Step 1: Write failing atomic cooler-command tests**

Append tests that prepare a synthetic cooler, replace `send_current_state` with an `AsyncMock`, invoke the driver command, and inspect state at send time:

```python
from custom_components.magiqtouch.const import (
    CONTROL_MODE_FAN,
    CONTROL_MODE_TEMP,
    MODE_COOLER,
    MODE_COOLER_FAN,
    ZONE_COMMON,
)


@pytest.mark.asyncio
async def test_temperature_command_atomically_selects_cooling_and_setpoint(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_FAN, set_temp=22.0)
    driver.current_state = make_remote_status(
        cooler=[cooler], running_mode=MODE_COOLER_FAN
    )
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_temperature(ZONE_COMMON, 26)

    assert driver.current_state.systemOn is True
    assert driver.current_state.runningMode == MODE_COOLER
    assert cooler.control_mode == CONTROL_MODE_TEMP
    assert cooler.set_temp == 26
    driver.send_current_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_speed_command_atomically_selects_cooling_and_speed(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(control_mode=CONTROL_MODE_TEMP, fan_speed=3)
    driver.current_state = make_remote_status(cooler=[cooler])
    driver.send_current_state = AsyncMock()

    await driver.set_cooling_by_speed(ZONE_COMMON, 8)

    assert driver.current_state.runningMode == MODE_COOLER
    assert cooler.control_mode == CONTROL_MODE_FAN
    assert cooler.fan_speed == 8
    driver.send_current_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_air_only_speed_change_retains_air_only_mode(
    driver, make_unit, make_remote_status
) -> None:
    cooler = make_unit(fan_speed=3)
    driver.current_state = make_remote_status(
        cooler=[cooler], running_mode=MODE_COOLER_FAN
    )
    driver.send_current_state = AsyncMock()

    await driver.set_current_speed(7, ZONE_COMMON)

    assert driver.current_state.runningMode == MODE_COOLER_FAN
    assert cooler.fan_speed == 7
    driver.send_current_state.assert_awaited_once()
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv311\Scripts\python.exe -m pytest tests\test_magiqtouch.py -k "temperature_command_atomically or speed_command_atomically or air_only_speed_change" -v
```

Expected: the first two tests fail because the methods do not accept temperature or speed, and the air-only test exposes the current non-zone-aware all-equipment mutation.

- [ ] **Step 3: Implement optional atomic values**

Change the driver methods so values are applied before the existing single `set_cooling()` or `set_heating()` send:

```python
async def set_heating_by_temperature(self, zone=ZONE_NONE, temperature=None):
    for heater in self.available_heaters(zone):
        heater.control_mode = CONTROL_MODE_TEMP
        if temperature is not None:
            heater.set_temp = round(float(temperature))
    await self.set_heating(zone)

async def set_heating_by_speed(self, zone=ZONE_NONE, speed=None):
    for heater in self.available_heaters(zone):
        heater.control_mode = CONTROL_MODE_FAN
        if speed is not None:
            heater.fan_speed = int(speed)
    await self.set_heating(zone)

async def set_cooling_by_temperature(self, zone=ZONE_NONE, temperature=None):
    for cooler in self.available_coolers(zone):
        cooler.control_mode = CONTROL_MODE_TEMP
        if temperature is not None:
            cooler.set_temp = round(float(temperature))
    await self.set_cooling(zone)

async def set_cooling_by_speed(self, zone=ZONE_NONE, speed=None):
    for cooler in self.available_coolers(zone):
        cooler.control_mode = CONTROL_MODE_FAN
        if speed is not None:
            cooler.fan_speed = int(speed)
    await self.set_cooling(zone)
```

Make `set_current_speed` select the equipment family from `runningMode`, mutate only those zone units, and build the checker with `units="c"` for cooler modes or `units="h"` for heater modes:

```python
async def set_current_speed(self, speed, zone=ZONE_NONE):
    speed = int(speed)
    running_mode = self.current_state.runningMode
    if running_mode in (MODE_COOLER, MODE_COOLER_FAN):
        units = self.available_coolers(zone)
        unit_type = "c"
    elif running_mode in (MODE_HEATER, MODE_HEATER_FAN):
        units = self.available_heaters(zone)
        unit_type = "h"
    else:
        raise ValueError(f"fan speed unavailable in mode: {running_mode}")
    for unit in units:
        unit.fan_speed = speed
    checker = partial(
        self.state_checker,
        units=unit_type,
        zone=zone,
        field="fan_speed",
        value=speed,
    )
    await self.send_current_state(checker)
```

- [ ] **Step 4: Run driver tests and verify GREEN**

Run:

```powershell
.\.venv311\Scripts\python.exe -m pytest tests\test_magiqtouch.py -v
```

Expected: all driver tests pass.

- [ ] **Step 5: Commit the atomic driver change**

```powershell
git add custom_components/magiqtouch/magiqtouch.py tests/test_magiqtouch.py
git commit -m "fix: send evaporative controls atomically"
```

### Task 2: Home Assistant Evaporative Mode Routing

**Files:**
- Modify: `custom_components/magiqtouch/climate.py:262-472`
- Test: `tests/test_climate.py`

**Interfaces:**
- Consumes: Task 1's optional temperature and speed parameters.
- Produces: `async_set_temperature()` that selects temperature control, numeric `async_set_fan_mode()` that selects manual cooling or updates air-only speed, and deterministic evaporative `fan_only` routing.

- [ ] **Step 1: Expand the synthetic controller and write failing climate tests**

Add mocks to `make_entity`:

```python
set_fan_only=AsyncMock(),
set_fan_only_evap=AsyncMock(),
set_fan_only_heater=AsyncMock(),
set_cooling=AsyncMock(),
set_heating=AsyncMock(),
set_on=AsyncMock(),
set_off=AsyncMock(),
set_temperature=AsyncMock(),
```

Add transition tests:

```python
@pytest.mark.asyncio
async def test_target_temperature_selects_evap_temperature_control(make_unit) -> None:
    entity, controller = make_entity(
        coolers=[make_unit(control_mode="FAN", fan_speed=5)]
    )

    await entity.async_set_temperature(temperature=25)

    controller.set_cooling_by_temperature.assert_awaited_once_with(
        entity.zone, 25
    )
    controller.set_temperature.assert_not_called()


@pytest.mark.asyncio
async def test_numeric_speed_selects_manual_evap_cooling(make_unit) -> None:
    entity, controller = make_entity(
        coolers=[make_unit(control_mode="TEMP")],
        running_mode=MODE_COOLER,
    )

    await entity.async_set_fan_mode("7")

    controller.set_cooling_by_speed.assert_awaited_once_with(entity.zone, "7")
    controller.set_current_speed.assert_not_called()


@pytest.mark.asyncio
async def test_numeric_speed_in_air_only_retains_air_only(make_unit) -> None:
    entity, controller = make_entity(
        coolers=[make_unit()],
        running_mode=MODE_COOLER_FAN,
    )

    await entity.async_set_fan_mode("6")

    controller.set_current_speed.assert_awaited_once_with("6", zone=entity.zone)
    controller.set_cooling_by_speed.assert_not_called()


@pytest.mark.asyncio
async def test_evap_only_fan_mode_explicitly_selects_fresh_air(make_unit) -> None:
    entity, controller = make_entity(coolers=[make_unit()])

    await entity.async_set_hvac_mode(HVACMode.FAN_ONLY)

    controller.set_fan_only_evap.assert_awaited_once_with(entity.zone)
    controller.set_fan_only_heater.assert_not_called()
```

Retain the existing assertion:

```python
assert entity.hvac_modes == [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.COOL]
```

- [ ] **Step 2: Run transition tests and verify RED**

Run:

```powershell
.\.venv311\Scripts\python.exe -m pytest tests\test_climate.py -k "target_temperature_selects or numeric_speed_selects or numeric_speed_in_air_only or evap_only_fan_mode" -v
```

Expected: failures show that temperature currently uses `set_temperature`, numeric speed does not select manual cooling, and fan-only delegates to mode history.

- [ ] **Step 3: Implement climate routing**

Route a target temperature through the installed/active equipment:

```python
equipment = self._fan_control_equipment()
if equipment == "cooler":
    await self.controller.set_cooling_by_temperature(self.zone, temperature)
elif equipment == "heater":
    await self.controller.set_heating_by_temperature(self.zone, temperature)
else:
    _LOGGER.warning("Cannot determine equipment for target temperature")
```

Route fan-only explicitly when only one equipment family is installed:

```python
if hvac_mode == HVACMode.FAN_ONLY:
    if self.cooler and not self.heater:
        await self.controller.set_fan_only_evap(self.zone)
    elif self.heater and not self.cooler:
        await self.controller.set_fan_only_heater(self.zone)
    else:
        await self.controller.set_fan_only(self.zone)
```

Route numeric speeds by the current running mode:

```python
elif self.controller.current_state.runningMode in (
    MODE_COOLER_FAN,
    MODE_HEATER_FAN,
):
    await self.controller.set_current_speed(fan_mode, zone=self.zone)
else:
    equipment = self._fan_control_equipment()
    if equipment == "cooler":
        await self.controller.set_cooling_by_speed(self.zone, fan_mode)
    elif equipment == "heater":
        await self.controller.set_heating_by_speed(self.zone, fan_mode)
    else:
        _LOGGER.warning(
            "Cannot determine active equipment for fan speed %s", fan_mode
        )
```

When `runningMode` is `COOLER_FAN` or `HEATER_FAN`, return only speeds 1-10 from `fan_modes`; temperature control is not meaningful in air-only mode.

- [ ] **Step 4: Run climate tests and verify GREEN**

Run:

```powershell
.\.venv311\Scripts\python.exe -m pytest tests\test_climate.py -v
```

Expected: all climate tests pass and the existing heating/cooling capability tests remain green.

- [ ] **Step 5: Commit the climate mapping**

```powershell
git add custom_components/magiqtouch/climate.py tests/test_climate.py
git commit -m "feat: map evaporative operating modes"
```

### Task 3: Documentation and Repository Verification

**Files:**
- Modify: `Readme.md`
- Verify: `.github/workflows/validate.yaml`

**Interfaces:**
- Consumes: the climate controls completed in Tasks 1 and 2.
- Produces: user-facing instructions and current validation evidence.

- [ ] **Step 1: Document evaporative-only controls**

Add this table under the README platform description:

```markdown
### Evaporative coolers

For an evaporative-only installation, Home Assistant exposes:

| Home Assistant control | MagIQtouch operation |
| --- | --- |
| Cool + target temperature | Evaporative cooling to the selected temperature |
| Cool + fan speed 1-10 | Evaporative cooling at a fixed fan speed |
| Fan only + fan speed 1-10 | Outside-air ventilation without evaporative cooling |
| Off | System off |

Heating is only shown when heater equipment is reported by the controller.
```

- [ ] **Step 2: Run the complete local verification**

Run:

```powershell
.\.venv311\Scripts\python.exe -m pytest -q
.\.venv311\Scripts\python.exe -m ruff check custom_components/magiqtouch tests
.\.venv311\Scripts\python.exe -m ruff format --check custom_components/magiqtouch tests
.\.venv311\Scripts\python.exe -m compileall -q custom_components/magiqtouch tests
.\.venv311\Scripts\python.exe -m pip check
git diff --check
```

Expected: all tests pass, Ruff reports no errors or formatting changes, compilation and dependency checks exit zero, and Git reports no whitespace errors.

- [ ] **Step 3: Commit documentation**

```powershell
git add Readme.md
git commit -m "docs: explain evaporative controls"
```

- [ ] **Step 4: Inspect final branch state**

Run:

```powershell
git status --short --branch
git log --oneline -5
git diff HEAD~3..HEAD --stat
```

Expected: the worktree is clean and the three implementation commits are visible on `codex/upstream-hardening`.
