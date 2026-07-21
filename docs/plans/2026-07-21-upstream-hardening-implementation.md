# MagIQtouch Upstream Hardening Implementation Plan

> **For Codex:** Execute this plan task by task using the test-driven-development,
> systematic-debugging, requesting-code-review, and verification-before-completion skills.

**Goal:** Produce an upstream-reviewable branch that hardens MagIQtouch cloud state handling and
correctly represents cooling-only, heating-only, temperature-controlled, and manual-fan systems.

**Architecture:** Retain the existing cloud driver and full-state command model. Harden the
boundaries where cloud data enters the integration, make WebSocket outcomes explicit, await
coordinator refreshes, and route climate commands from reported equipment capabilities and
running mode. Keep external Home Assistant temperature sensors as a later automation layer.

**Tech stack:** Python 3.12, Home Assistant custom integration APIs, aiohttp, pytest,
pytest-asyncio, Ruff, GitHub Actions.

---

## Task 1: Establish the test environment

**Files:**

- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`

**Step 1: Declare test dependencies and configuration**

Add a `test` optional dependency group containing `pytest` and `pytest-asyncio`. Add pytest
configuration with `testpaths = ["tests"]` and `asyncio_mode = "auto"`. Add `.venv/` to
`.gitignore`.

**Step 2: Add common state fixtures**

In `tests/conftest.py`, provide small fixtures/builders for:

- a `UnitDetails` evaporative cooler;
- a `UnitDetails` heater;
- `RemoteStatus` with installed capability flags;
- an `AsyncMock` controller suitable for climate entity tests.

Keep payloads synthetic and free of device IDs, credentials, or captured customer data.

**Step 3: Create and populate the local environment**

Run:

```powershell
$py = 'C:\Users\JLowes\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Expected: installation succeeds under Python 3.12. Do not use the machine's Python 3.14 because
the repository currently pins Home Assistant 2024.2.5.

**Step 4: Verify test discovery**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: pytest starts successfully; zero tests is acceptable at this infrastructure step.

**Step 5: Commit**

```powershell
git add .gitignore pyproject.toml tests/conftest.py
git commit -m "Add first-party test infrastructure"
```

## Task 2: Make cloud state parsing forward-compatible

**Files:**

- Create: `tests/test_structures.py`
- Modify: `custom_components/magiqtouch/structures.py`

**Step 1: Write failing parser tests**

Cover:

- an unknown top-level `RemoteStatus` field is ignored;
- an unknown field inside a cooler/heater record is ignored;
- declared nested dataclasses still convert correctly;
- a genuinely missing required dataclass field raises instead of returning the input mapping.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_structures.py -q
```

Expected: unknown-field and missing-required-field tests fail against the current helper.

**Step 2: Implement field filtering**

Refactor `dataclass_from_dict` to:

- detect dataclass targets explicitly;
- pass only declared keys to dataclass constructors;
- recursively convert declared nested dataclasses;
- preserve list and scalar values that do not require conversion;
- let constructor errors for missing required fields propagate.

Use the same declared-field filtering for `UnitDetails` entries in `RemoteStatus.from_dict`.

**Step 3: Verify the parser tests**

Run the Task 2 pytest command again.

Expected: all parser tests pass.

## Task 3: Reconcile changing equipment lists safely

**Files:**

- Modify: `tests/test_structures.py`
- Modify: `custom_components/magiqtouch/structures.py`

**Step 1: Write failing reconciliation tests**

Cover cooler/heater lists that:

- gain a zone;
- lose a zone;
- arrive in a different order;
- update matching units in place, preserving object identity.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_structures.py -q
```

Expected: growth raises `IndexError`, and reorder/shrink expectations fail.

**Step 2: Implement identity-based reconciliation**

Add a small private helper that indexes existing units by `(zoneType, name)`, updates matching
dataclasses in place, inserts new units in incoming order, and removes absent units. Use it for
both `cooler` and `heater` in `RemoteStatus.update`.

**Step 3: Verify and commit Tasks 2-3**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_structures.py -q
git diff --check
git add custom_components/magiqtouch/structures.py tests/test_structures.py
git commit -m "Harden cloud state parsing and reconciliation"
```

Expected: tests and diff check pass before the commit is created.

## Task 4: Correct WebSocket timeout and failure semantics

**Files:**

- Create: `tests/test_magiqtouch.py`
- Modify: `custom_components/magiqtouch/magiqtouch.py`

**Step 1: Write failing WebSocket tests**

Use fake async WebSocket/session objects and monkeypatching to cover:

- `ws_send(..., timeout=8)` stores an eight-second duration, not `time.time() + 8`;
- a no-message receive timeout makes `ws_send` return `False`;
- a background refresh that received and processed state before its receive window closes counts
  as successful completion;
- timed-out and failed jobs are removed from `driver.jobs`;
- unexpected connection errors do not produce a successful `True` result.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_magiqtouch.py -q
```

Expected: duration and failure-result tests fail against the current implementation.

**Step 2: Implement explicit lifecycle handling**

Change `WebsocketJob.timeout` to hold a duration. In `ws_handler`:

- initialise the socket variable before entering the connection context;
- pass the duration to `aiohttp.ClientWSTimeout`;
- distinguish an idle timeout from normal completion after a background state response;
- re-raise actionable timeout/connection failures;
- remove the job in a `finally` block.

Keep `ws_send` as the boolean boundary used by existing command recovery logic.

**Step 3: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_magiqtouch.py -q
git diff --check
git add custom_components/magiqtouch/magiqtouch.py tests/test_magiqtouch.py
git commit -m "Fix WebSocket timeout handling"
```

## Task 5: Preserve authentication errors and await coordinator refreshes

**Files:**

- Create: `tests/test_config_flow.py`
- Create: `tests/test_coordinator.py`
- Modify: `custom_components/magiqtouch/config_flow.py`
- Modify: `custom_components/magiqtouch/magiqtouch.py`
- Modify: `custom_components/magiqtouch/__init__.py`

**Step 1: Write failing authentication tests**

Monkeypatch the driver used by `validate_input` and cover:

- `login()` returning `False` raises `InvalidAuth`;
- an `InvalidSignatureException`-style error raises `InvalidTime`;
- an unrelated network/client error raises `CannotConnect` with the original exception chained.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_flow.py -q
```

Expected: the invalid-auth case is incorrectly converted to `CannotConnect` before the fix.

**Step 2: Preserve typed config-flow failures**

Add explicit `except InvalidAuth: raise` handling before the generic exception mapping. Raise
`InvalidTime` and `CannotConnect` using exception chaining and avoid logging credential-adjacent
trace content at error level.

**Step 3: Write failing refresh tests**

Cover:

- `MagIQtouch_Driver.refresh_state()` awaits `full_refresh()` directly;
- coordinator refresh retries once after re-login;
- a failed retry raises Home Assistant `UpdateFailed` rather than reporting success.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_coordinator.py -q
```

Expected: the direct-await and failure-propagation tests fail against the current detached task.

**Step 4: Implement awaited refresh and retry semantics**

Make `refresh_state` await `full_refresh` directly while leaving `background_refresh` available
for intentionally detached state listening after a command. Update `_async_update_data` to retry
once after login and raise `UpdateFailed` if refresh still fails.

**Step 5: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_flow.py tests/test_coordinator.py -q
git diff --check
git add custom_components/magiqtouch/config_flow.py custom_components/magiqtouch/magiqtouch.py custom_components/magiqtouch/__init__.py tests/test_config_flow.py tests/test_coordinator.py
git commit -m "Fix authentication and coordinator refresh errors"
```

## Task 6: Make climate behaviour capability-driven

**Files:**

- Create: `tests/test_climate.py`
- Modify: `custom_components/magiqtouch/climate.py`

**Step 1: Write failing mode-routing tests**

Cover:

- cooling-only master entities expose `off`, `cool`, and supported `fan_only`, never `heat`;
- heating-only master entities expose `off`, `heat`, and supported `fan_only`, never `cool`;
- `Temperature` routes to cooling temperature control while cooling;
- `Temperature` routes to heating temperature control while heating;
- `Previous` routes back to the corresponding cooling/heating manual-speed method;
- when off, a single installed equipment type is a safe fallback;
- when off with both heating and cooling installed, the integration logs and does not guess;
- numeric fan modes call `set_current_speed` unchanged.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_climate.py -q
```

Expected: heating `Temperature` and `Previous` tests fail because both currently call cooling
methods.

**Step 2: Implement an equipment-route helper**

Add one private method that resolves `cooler`, `heater`, or `None` from the running mode and
installed/available equipment. Use it from `async_set_fan_mode` to call the matching controller
method. Return after logging when the equipment type is genuinely ambiguous.

Do not remove any existing heating capability to optimise for the target evaporative system.

**Step 3: Write failing temperature-availability tests**

Cover:

- a valid internal temperature is returned;
- valid readings across multiple units are averaged;
- sentinel readings are excluded from the average;
- no active/inactive units returns `None` rather than raising;
- no valid reading returns `None`, never the target temperature;
- no unit returns `None` for target/min/max properties;
- manual fan control remains a supported feature when no temperature is available.

**Step 4: Implement safe temperature access**

Add small helpers for selecting relevant units and validating controller temperatures. Remove
the target-temperature fallback from `current_temperature`. Make target/min/max properties
return `None` when equipment state is unavailable, and ensure unit capability initialisation
occurs before supported features are calculated.

**Step 5: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_climate.py -q
git diff --check
git add custom_components/magiqtouch/climate.py tests/test_climate.py tests/conftest.py
git commit -m "Route climate controls by installed capability"
```

## Task 7: Add CI and correct repository metadata

**Files:**

- Modify: `.github/workflows/validate.yaml`
- Modify: `custom_components/magiqtouch/manifest.json`
- Modify: `Readme.md`

**Step 1: Add local validation coverage**

Extend the workflow with a test job that checks out the repository, selects a compatible Python
version, installs `.[test]`, runs pytest, and runs Ruff lint against first-party code and tests.
Pin GitHub Action major versions rather than floating repository branches where practical.

**Step 2: Correct repository links**

Point documentation and issue-tracker metadata at
`https://github.com/andrewleech/ha_magiqtouch`. Preserve maintainer-controlled release versioning
rather than inventing a new release number.

**Step 3: Validate workflow and metadata**

Run:

```powershell
.\.venv\Scripts\python.exe -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('custom_components/magiqtouch').rglob('*.json')]"
.\.venv\Scripts\python.exe -m ruff check custom_components/magiqtouch tests
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: JSON, lint, tests, and whitespace checks all pass.

**Step 4: Commit**

```powershell
git add .github/workflows/validate.yaml custom_components/magiqtouch/manifest.json Readme.md
git commit -m "Add upstream validation workflow"
```

## Task 8: Full verification and upstream review preparation

**Files:**

- Review all files changed from `origin/hacs`
- Update design/plan docs only if implementation decisions materially changed

**Step 1: Run the full verification suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check custom_components/magiqtouch tests
.\.venv\Scripts\python.exe -m compileall -q custom_components/magiqtouch
.\.venv\Scripts\python.exe -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('custom_components/magiqtouch').rglob('*.json')]"
git diff --check origin/hacs...HEAD
git status --short --branch
```

Expected: all commands exit zero and the working tree is clean.

**Step 2: Review scope and safety**

Inspect:

```powershell
git log --oneline origin/hacs..HEAD
git diff --stat origin/hacs...HEAD
git diff origin/hacs...HEAD -- custom_components/magiqtouch tests .github Readme.md docs/plans
```

Confirm:

- no HA-Air files changed;
- no credentials or real cloud payloads were added;
- no heater support was removed;
- no unsupported partial-state command was introduced;
- vendored dependencies remain an explicitly documented follow-up.

**Step 3: Request code review and address findings**

Use the requesting-code-review skill on the complete branch. For each finding, reproduce it or
verify it against the implementation before changing code. Re-run the relevant focused tests,
then the full suite.

**Step 4: Prepare the handoff**

Report the branch, commits, exact test results, remaining live-controller verification, and the
vendored dependency follow-up. Do not push or open a pull request without the user's explicit
authorization.

