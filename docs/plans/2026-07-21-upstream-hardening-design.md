# MagIQtouch Upstream Hardening Design

Date: 2026-07-21

## Context

The integration supports Seeley MagIQtouch systems through the vendor cloud API. The
immediate target installation is an evaporative cooler with no heater, but the upstream
integration must continue to support heating, refrigerated cooling, evaporative cooling,
fan-only operation, and zoned systems.

The target controller is not yet available for live testing. The design therefore separates
deterministic protocol and entity behaviour, which can be covered by fixtures, from a short
hardware verification checklist to run after installation.

## Goals

- Correct the selected transport, parsing, refresh, authentication, and climate-control
  defects without redesigning the cloud protocol.
- Treat installed capabilities and live controller state as the source of truth.
- Support cooling-only systems without removing or weakening heating support.
- Preserve both thermostat-driven (`TEMP`) and manual fan-speed control.
- Add focused automated tests and CI so the changes are reviewable upstream.
- Keep future Home Assistant sensor-based control outside the device integration.

## Non-goals

- Replacing the cloud API with local control.
- Rewriting the integration around a new client library.
- Making unrelated Home Assistant temperature entities dependencies of MagIQtouch.
- Replacing all vendored authentication dependencies in the behavioural-fix change set.
- Redesigning the full-state command transaction to eliminate every race with changes made from
  the wall controller or official app; that requires live-device timing evidence.
- Claiming live-device compatibility before the target controller is installed.

## Approach

Use a capability-driven hardening change set. Existing state structures and command methods
remain in place, but their boundaries become stricter and are covered by tests. This creates a
small enough upstream review surface while addressing the defects that can lose state or send
the wrong command.

The vulnerable vendored dependency bundle will be handled as a separate follow-up because it
has a different risk profile and produces a large diff unrelated to climate behaviour.

## Design

### 1. Test foundation

Add a first-party `tests/` suite using `pytest` and `pytest-asyncio`. Fixtures will represent:

- evaporative cooling with temperature control;
- evaporative cooling with manual fan-speed control;
- heating with temperature and manual fan-speed control;
- an unknown future cloud field;
- a controller whose reported zone count grows;
- successful WebSocket responses and receive timeouts.

Tests will exercise public or stable internal boundaries rather than making real cloud calls.
Home Assistant entity tests will use lightweight controller doubles containing the state used by
the climate entity.

CI will run the test suite and Ruff alongside the existing HACS and hassfest validation jobs.

### 2. WebSocket request lifecycle

Timeouts are durations, not wall-clock timestamps. A request job will retain the configured
timeout duration and pass it to `aiohttp.ClientWSTimeout.ws_receive` unchanged.

If a receive timeout occurs, the request must fail visibly. The WebSocket handler will re-raise
`asyncio.TimeoutError` after cleanup so `ws_send` can return `False`. A refresh that receives
`False` will raise an update error through the coordinator. A command that receives `False`
will retain the existing recovery behaviour of requesting a state resynchronisation.

Successful responses continue to resolve the matching job exactly once.

### 3. Forward-compatible state parsing

`dataclass_from_dict` will ignore input keys that are not declared dataclass fields. Declared
fields retain the existing recursive conversion behaviour. The same filtering will apply when
constructing nested `UnitDetails` records. Missing required fields will still fail, since
silently inventing required protocol state would conceal an incompatible response.

This allows Seeley to add fields without taking the integration offline while retaining useful
validation of fields the integration depends on.

### 4. Dynamic zone-state reconciliation

`RemoteStatus.update` will reconcile equipment lists by stable identity (`zoneType` and `name`)
while allowing the incoming list to grow, shrink, or reorder. Matching entries will be updated
in place; new entries will be inserted, and entries no longer present will be removed.

This preserves object identity for active entities while preventing `IndexError` when the cloud
reports a newly discovered zone.

### 5. Authentication and refresh errors

The config flow will preserve known authentication failures as `InvalidAuth` and clock/signature
failures as `InvalidTime`. Only connectivity and unclassified client failures become
`CannotConnect`. This gives users the correct remediation instead of reporting bad credentials
as a network problem.

Coordinator refresh will await the actual full refresh. It will no longer report a completed
coordinator cycle immediately after scheduling detached work. Exceptions will therefore flow
through Home Assistant's normal update-failure path and overlapping refresh tasks will be
reduced.

The protocol requires a full state blob for commands. This change will preserve the existing
initial refresh guard and will not replace full-state commands with unsupported partial updates.

### 6. Capability-driven climate behaviour

The integration will continue to derive Home Assistant HVAC modes from installed controller
capabilities:

- cooling-only: `off`, `cool`, and `fan_only` where supported;
- heating-only: `off`, `heat`, and `fan_only` where supported;
- combined systems: the union of their installed modes.

Selecting the `Temperature` fan mode will switch the active equipment type to its temperature
control method. Selecting `Previous` will switch the active equipment type back to manual speed
control. The current implementation always calls cooling methods; the corrected routing will
use the current running mode and available equipment so a heating system cannot be switched to
cooling accidentally.

For an evaporative-only system, `Temperature` maps to evaporative temperature control and
numeric fan modes map to manual evaporative fan speed. No heater will be exposed or addressed
when one is not installed.

Current and target temperature will only be exposed when the controller provides a plausible
value. Sentinel or unavailable readings will become `None` rather than a fabricated room
temperature. Manual fan control remains usable when temperature is unavailable.

### 7. External Home Assistant sensors

Other room temperature sensors belong in a later Home Assistant automation or helper layer.
That layer may select a MagIQtouch target temperature or map measured conditions to a manual fan
speed. Keeping this outside the integration avoids cross-integration entity dependencies and
keeps the upstream component representative of the physical device.

### 8. Repository metadata

Update stale documentation and issue-tracker links to the current GitHub repository. Do not
invent a release version; the maintainer remains responsible for release numbering. Formatting
and lint changes will be limited to files touched by the behavioural fixes.

## Error handling

- Network timeouts and cloud failures propagate to the coordinator or command caller.
- Unknown response fields are tolerated and ignored.
- Missing required response data remains an error.
- Invalid credentials remain distinguishable from connectivity failures.
- Climate commands that cannot be routed to installed/current equipment log a clear warning and
  do not guess an equipment type.

## Change structure

The local branch will contain reviewable commits in this order:

1. Test infrastructure and protocol fixtures.
2. Transport, parser, state-reconciliation, authentication, and refresh fixes.
3. Capability-driven climate fixes and their entity tests.
4. CI and repository metadata updates.

The vendored dependency replacement will be documented as a follow-up and kept out of these
commits.

## Verification

Before the branch is considered ready for upstream review:

- all new tests pass;
- Ruff lint and formatting checks pass for first-party code;
- every first-party Python file compiles;
- JSON metadata and translations parse;
- HACS and hassfest validation configuration remains valid;
- the diff contains no credentials, recorded cloud payloads, or unrelated HA-Air changes.

After the physical controller is installed, verify:

- discovered installed capabilities and available HVAC modes;
- whether `internal_temp` is populated;
- `TEMP` mode target changes;
- manual fan speeds across the supported range;
- fan-only ventilation;
- state refresh after commands and after changes made in the official app.
