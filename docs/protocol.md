# MagIQtouch WebSocket and REST API Protocol Specification

This document describes the protocol used by Seeley MagIQtouch heating/cooling controllers, as reverse-engineered from the iOS app traffic and the ha_magiqtouch Home Assistant integration codebase.

Source files referenced throughout:
- `custom_components/magiqtouch/magiqtouch.py` -- driver, WebSocket handling, command construction
- `custom_components/magiqtouch/structures.py` -- data structures (RemoteStatus, SystemDetails, etc.)
- `custom_components/magiqtouch/const.py` -- mode constants, zone types
- `custom_components/magiqtouch/vendor/mandate/client.py` -- Cognito auth HTTP calls
- `custom_components/magiqtouch/vendor/mandate/aws_srp.py` -- SRP cryptographic operations
- `develop/dump/` -- captured JSON state messages
- `develop/sequence/` -- captured WebSocket traffic and device logs

---

## 1. Authentication

Authentication uses AWS Cognito User Pools with the Secure Remote Password (SRP) protocol. No AWS SigV4 request signing is required -- the Cognito API calls used (InitiateAuth, RespondToAuthChallenge) are unauthenticated public API calls.

### AWS Cognito Parameters

| Parameter          | Value                                  |
|--------------------|----------------------------------------|
| Region             | `ap-southeast-2`                       |
| User Pool ID       | `ap-southeast-2_uw5VVNlib`             |
| Client ID          | `afh7fftbb0fg2rnagdbgd9b7b`           |
| Endpoint           | `https://cognito-idp.ap-southeast-2.amazonaws.com/` |

Source: `magiqtouch.py` lines 43-46.

### SRP Authentication Flow

All requests are HTTP POST to the Cognito endpoint with these headers:

```
Content-Type: application/x-amz-json-1.1
X-Amz-Target: AWSCognitoIdentityProviderService.<OperationName>
```

Source: `vendor/mandate/client.py` lines 11-14, 43-58.

#### Step 1: InitiateAuth

Request:

```json
{
    "AuthFlow": "USER_SRP_AUTH",
    "ClientId": "afh7fftbb0fg2rnagdbgd9b7b",
    "AuthParameters": {
        "USERNAME": "<email>",
        "SRP_A": "<hex-encoded public value A>"
    }
}
```

`X-Amz-Target`: `AWSCognitoIdentityProviderService.InitiateAuth`

The client generates a random value `a`, computes `A = g^a mod N` using the standard SRP parameters (3072-bit prime from RFC 5054), and sends the hex-encoded `A` value.

Source: `vendor/mandate/aws_srp.py` lines 99-176.

Response contains `ChallengeName: "PASSWORD_VERIFIER"` and `ChallengeParameters`:

| Parameter              | Description                           |
|------------------------|---------------------------------------|
| `USER_ID_FOR_SRP`      | The username (may differ from input)  |
| `SALT`                 | Hex-encoded salt                      |
| `SRP_B`                | Hex-encoded server public value B     |
| `SECRET_BLOCK`         | Base64-encoded secret block           |

#### Step 2: RespondToAuthChallenge

The client computes the password claim using HKDF over the SRP shared secret, then signs a message consisting of the pool ID suffix + username + secret block + timestamp.

Request:

```json
{
    "ClientId": "afh7fftbb0fg2rnagdbgd9b7b",
    "ChallengeName": "PASSWORD_VERIFIER",
    "ChallengeResponses": {
        "TIMESTAMP": "Mon Mar 14 13:22:34 UTC 2024",
        "USERNAME": "<user_id_for_srp>",
        "PASSWORD_CLAIM_SECRET_BLOCK": "<base64 secret block from step 1>",
        "PASSWORD_CLAIM_SIGNATURE": "<base64 HMAC-SHA256 signature>"
    }
}
```

`X-Amz-Target`: `AWSCognitoIdentityProviderService.RespondToAuthChallenge`

Note: the timestamp format strips leading zeros from single-digit day numbers (e.g., `" 5 "` becomes `" 5 "`, not `" 05 "`). This is required by Cognito.

Source: `vendor/mandate/aws_srp.py` lines 185-214.

Response on success:

```json
{
    "AuthenticationResult": {
        "AccessToken": "<jwt>",
        "IdToken": "<jwt>",
        "RefreshToken": "<opaque token>",
        "TokenType": "Bearer",
        "ExpiresIn": 3600
    }
}
```

Three tokens are returned:
- **AccessToken**: Used for Cognito user operations. JWT with ~1 hour lifetime.
- **IdToken**: Used for API Gateway authorization (REST and WebSocket). JWT with ~1 hour lifetime.
- **RefreshToken**: Long-lived token for obtaining new access/ID tokens without re-authenticating.

Source: `vendor/mandate/client.py` lines 122-162.

### Token Refresh

When the access token expires (checked via the JWT `exp` claim), a refresh is performed:

Request:

```json
{
    "AuthFlow": "REFRESH_TOKEN",
    "ClientId": "afh7fftbb0fg2rnagdbgd9b7b",
    "AuthParameters": {
        "REFRESH_TOKEN": "<refresh_token>"
    }
}
```

`X-Amz-Target`: `AWSCognitoIdentityProviderService.InitiateAuth`

Response returns new `AccessToken`, `IdToken`, and `TokenType`. The refresh token itself is not rotated.

Source: `vendor/mandate/client.py` lines 164-180.

### Token Lifetime

The access and ID tokens expire after approximately 1 hour (Cognito default). The WebSocket handler monitors connection duration and restarts the connection before the 45-minute mark to avoid mid-session expiry.

Source: `magiqtouch.py` lines 265-269.

---

## 2. REST API

### Base URL

```
https://tgjgb3bcf3.execute-api.ap-southeast-2.amazonaws.com/prod/v1/
```

Source: `magiqtouch.py` line 50. An older API URL (`https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com/api/`) is referenced but marked obsolete.

### GET /devices/system

Returns system configuration and device information.

**Headers:**

```
Authorization: Bearer <id_token>
```

Source: `magiqtouch.py` lines 294-320.

**Response:**

A JSON array with a single element containing a `SystemDetails` object. The response is accessed as `(await rsp.json())[0]`.

Example (redacted):

```json
[
    {
        "ACZones": {
            "Manual": true,
            "SlaveWallControls": false,
            "Zones": []
        },
        "AOCFixed": {
            "InSystem": false,
            "MaximumTemperature": 28,
            "MinimumTemperature": 18
        },
        "AOCInverter": {
            "MaximumTemperature": 28,
            "MinimumTemperature": 18,
            "InSystem": false
        },
        "Cabinets": [
            {
                "CabinetSerialNo": 1256799,
                "CoolerCabinetSoftRev": "28R0922",
                "ElectronicsSerialNo": " ",
                "ModelNumber": "LPQI 550"
            }
        ],
        "EVAPCooler": {
            "Brands": 3,
            "HumidityControl": false,
            "MaximumTemperature": 28,
            "MinimumTemperature": 18,
            "TemperatureUnits": 0
        },
        "WallController": {
            "Firmware": "44R0222",
            "Type": 0
        },
        "Heater": {
            "InSystem": true,
            "FixedFan": false,
            "Brands": 3,
            "DataTableVersion": "D0.0",
            "ICSSoftwareRev": "V1.11",
            "MaxSetFanSpeed": 10,
            "MaximumTemperature": 37,
            "MinimumTemperature": 0,
            "ModelNo": "TQS6X23N",
            "SerialNo": 1125671
        },
        "MasterAirSensorPresent": false,
        "SlaveWallControls": 0,
        "NoOfZoneControls": 1,
        "System": {
            "configuration": 2,
            "cooler": {"available": true, "fanFixed": false},
            "heater": {"available": true, "fanFixed": false},
            "fan": {"available": true, "fanFixed": false},
            "Address": "<street address>",
            "Name": "<system name>"
        },
        "Wifi_Module": {
            "MacAddressId": "<mac_address>",
            "version": "1.7",
            "type": "WI-FI IoT Device"
        },
        "ExternalAirSensorPresent": false,
        "DamperDelayModulePresent": false,
        "BMSS1": false,
        "BMSMS1": false,
        "ZoneAirSensors": 0
    }
]
```

The `Wifi_Module.MacAddressId` value is used as the device identifier for all subsequent WebSocket communication.

Source: `develop/sequence/Log_1_Dul90.log` line 2, `structures.py` lines 324-355.

---

## 3. WebSocket API

### Connection

**URL:**

```
wss://xs5z2412cf.execute-api.ap-southeast-2.amazonaws.com/prod?token=<id_token>
```

The ID token (not the access token) is passed as a query parameter.

Source: `magiqtouch.py` line 52.

**Headers:**

```
user-agent: Dart/3.2 (dart:io)
sec-websocket-protocol: wasp
```

Source: `magiqtouch.py` line 188.

The connection is established using standard WebSocket upgrade. Auto-ping is disabled. The client manages connection lifecycle and reconnects as needed.

### Message Types

There are two outbound message types (client to server) and one inbound message type (server to client).

#### 3.1 Status Request

Requests the current device state. The server responds with a stream of `RemoteStatus` messages.

```json
{
    "action": "status",
    "params": {
        "device": "<mac_address>"
    }
}
```

After sending a status request, the server sends multiple `RemoteStatus` messages (observed: 5-6 messages in quick succession, then periodic updates). The WebSocket remains open and continues to receive state updates as the device state changes.

Source: `magiqtouch.py` lines 326-329, 357-373.

#### 3.2 Command

Sends a new desired state to the device. The `params` field contains a full `RemoteStatus` object.

```json
{
    "action": "command",
    "params": {
        "device": "<mac_address>",
        "timestamp": 1710912802094,
        "online": true,
        "systemOn": true,
        "runningMode": "HEAT",
        "heaterFault": false,
        "coolerFault": false,
        "cooler": [ ... ],
        "heater": [ ... ],
        "fan": { ... },
        "touchCount": 241,
        "installed": { ... }
    }
}
```

The `timestamp` field is set to the current UTC epoch time (in seconds, not milliseconds) before sending.

Source: `magiqtouch.py` lines 407-417.

#### 3.3 Response (Server to Client)

All server messages are `RemoteStatus` JSON objects (no wrapper -- the raw object, not wrapped in `action`/`params`). The same format is used for responses to both status requests and commands.

The client parses each message with `RemoteStatus.from_dict(data)`.

Source: `magiqtouch.py` lines 230-234.

### Connection Lifecycle

1. A new WebSocket connection is opened for each operation (status request or command).
2. For commands: the client sends the message, waits for a response matching expected state via a `checker` callback, then closes the connection.
3. For background refresh: the client sends a status request and keeps the connection open, processing all incoming state updates.
4. When a command is sent, any existing background refresh WebSocket is closed first to prevent stale state from overriding the command.
5. After a command is confirmed, a new background refresh WebSocket is started.
6. If a command is not confirmed within the timeout (default 8 seconds), a background refresh is triggered to resync local state.

Source: `magiqtouch.py` lines 160-287.

---

## 4. Partial State Commands

Partial state commands (sending only a subset of `RemoteStatus` fields) were tested but **do not work** for actual state changes.

### Test Results

A minimal command with only `device`, `timestamp`, and `systemOn` was sent:

```json
{
    "action": "command",
    "params": {
        "device": "<mac_address>",
        "timestamp": 1710912802094,
        "systemOn": true
    }
}
```

The command reached the device (confirmed by `touchCount` incrementing) but did not change state. No WebSocket response was received, and the device remained off. A subsequent no-op test (sending the same `systemOn` value as current state) also produced no response.

An earlier test appeared to show success (3 responses received), but these were background status stream messages coinciding with the command, not command confirmations.

### Conclusion

The server/device requires the full state blob to process a command. The full-state-overwrite model documented in Section 6 is required, not optional. This means the #35 issue (stale zone state being sent with `set_on`) cannot be solved by sending partial state.

---

## 5. Data Structures

### 5.1 RemoteStatus

The top-level state object for a device. Sent by the server as WebSocket messages and sent by the client as `params` in command messages.

Source: `structures.py` lines 429-487.

| Field          | Type              | Example                | Writable | Notes |
|----------------|-------------------|------------------------|----------|-------|
| `device`       | string            | `"90e202cadd0c"`       | Yes (identifies target) | MAC address, lowercase hex, no separators |
| `timestamp`    | integer           | `1710912802094`        | Yes (set before send) | Milliseconds from device; client sets seconds-precision UTC epoch on commands |
| `online`       | boolean           | `true`                 | Read-only | Device online status |
| `systemOn`     | boolean           | `false`                | Yes | Master on/off for the entire system |
| `runningMode`  | string            | `"HEAT"`               | Yes | One of: `"COOL"`, `"COOLER_FAN"`, `"HEAT"`, `"HEATER_FAN"` |
| `heaterFault`  | boolean           | `false`                | Read-only | |
| `coolerFault`  | boolean           | `false`                | Read-only | |
| `cooler`       | list[UnitDetails] | (see below)            | Yes | One entry per cooler zone |
| `heater`       | list[UnitDetails] | (see below)            | Yes | One entry per heater zone |
| `fan`          | Fan               | (see below)            | Read-only | System-level fan info |
| `touchCount`   | integer           | `528`                  | Unclear | Purpose unknown; increments over time, possibly a counter of physical button presses or state changes on the wall controller |
| `installed`    | Installed         | (see below)            | Read-only | Which device types are present |

Equality comparison (`__eq__`) ignores `timestamp` and any field containing "actual" in its name (i.e., sensor readings that change continuously).

Source: `structures.py` lines 477-487.

### 5.2 UnitDetails

Per-zone device state. Each entry in the `cooler` and `heater` arrays is a `UnitDetails` object.

Source: `structures.py` lines 362-385.

| Field                     | Type    | Example              | Writable | Notes |
|---------------------------|---------|----------------------|----------|-------|
| `brand`                   | integer | `3`                  | Read-only | |
| `name`                    | string  | `"Family Room"`      | Read-only | Zone name; COMMON zones may use `""` or `"COMMON ZONE"` |
| `runningState`            | string  | `"NOT_REQUIRED"`     | Yes | Values observed: `"NOT_REQUIRED"`, `"REQUIRED_RUNNING"` |
| `zoneRunningState`        | string  | `"NOT_REQUIRED"`     | Yes | Values observed: `"NOT_REQUIRED"`, `"REQUIRED_RUNNING"` |
| `zoneOn`                  | boolean/null | `true`/`false`/`null` | Yes | Zone enabled state. **COMMON zone devices always report `null`** (see Section 7) |
| `zoneType`                | string  | `"INDIVIDUAL"`       | Read-only | Values observed: `"COMMON"`, `"INDIVIDUAL"`, `"SLAVE"` |
| `set_temp`                | float   | `23`                 | Yes | Target temperature (integer in practice) |
| `temperature_units`       | string  | `"c"`                | Read-only | `"c"` for Celsius |
| `actual_temp`             | float   | `24`                 | Read-only | Current measured temperature |
| `max_temp`                | float/null | `28`              | Read-only | Maximum allowed set temperature. **Null for SLAVE zones** |
| `min_temp`                | float/null | `19`              | Read-only | Minimum allowed set temperature. **Null for SLAVE zones** |
| `fan_speed`               | integer | `1`                  | Yes | Current fan speed setting |
| `max_fan_speed`           | integer/null | `10`            | Read-only | Null for SLAVE zones |
| `min_fan_speed`           | integer/null | `1`             | Read-only | Null for SLAVE zones |
| `control_mode`            | string/null | `"TEMP"`, `"FAN"`, `null` | Yes | `"TEMP"` = temperature setpoint control, `"FAN"` = manual fan speed control. Null when not applicable |
| `control_mode_type`       | string  | `"MASTER"`, `"NONE"` | Read-only | |
| `internal_temp`           | float   | `23`                 | Read-only | Temperature reading from zone sensor |
| `external_temp`           | float/null | `null`            | Read-only | External temperature sensor; null when not present |
| `programMode`             | string/null | `"off"`          | Read-only | Null for SLAVE zones |
| `ProgramModeOverridden`   | boolean/null | `false`         | Read-only | Null for SLAVE zones |
| `ProgramPeriodActive`     | boolean/null | `false`         | Read-only | Null for SLAVE zones |
| `programOverrideDisabled` | boolean/null | `false`         | Read-only | Null for SLAVE zones |

#### Zone Types

Three zone types appear in captured data:

- **`"COMMON"`**: The master/common zone. Always present. Controls system-wide settings. `zoneOn` is always `null`. `control_mode_type` is `"MASTER"` for coolers, `"NONE"` for heaters.
- **`"INDIVIDUAL"`**: Zones with independent temperature sensors and damper control. Each has its own `set_temp`, `max_temp`, `min_temp`. Observed in multi-zone systems without slave wall controllers.
- **`"SLAVE"`**: Zones controlled by slave wall controllers. Most fields (`max_temp`, `min_temp`, `max_fan_speed`, `min_fan_speed`, `control_mode`, `programMode`, etc.) are `null`. Only `zoneOn`, `set_temp`, `fan_speed`, and temperature readings are populated.

Source: `develop/dump/cool_all_zones_off.json`, `develop/sequence/Log_1_Dul90.log`.

### 5.3 Fan

System-level fan information.

Source: `structures.py` lines 410-417.

| Field              | Type    | Example | Notes |
|--------------------|---------|---------|-------|
| `cooler_available` | boolean | `false` | Whether cooler fan mode is available |
| `cooler_brand`     | integer | `3`     | |
| `heater_available` | boolean | `true`  | Whether heater fan mode is available |
| `heater_brand`     | integer | `3`     | |
| `heater_Fan_Speed` | integer | `1`     | |
| `cooler_Fan_Speed` | integer | `1`     | |

### 5.4 Installed

Indicates which device types are present in the system.

Source: `structures.py` lines 420-426.

| Field        | Type    | Example | Notes |
|--------------|---------|---------|-------|
| `evap`       | boolean | `false` | Evaporative cooler installed |
| `faoc`       | boolean | `false` | Fixed add-on cooler installed |
| `heater`     | boolean | `true`  | Gas heater installed |
| `iaoc`       | boolean | `true`  | Inverter add-on cooler installed |
| `coolerType` | integer | `2`     | Encoding unclear; `0` observed with evap, `2` observed with iaoc |

### 5.5 SystemDetails

Static system configuration returned by the REST API. This does not change during normal operation.

Source: `structures.py` lines 324-355.

| Field                      | Type             | Notes |
|----------------------------|------------------|-------|
| `ACZones`                  | ACZonesDef       | Zone configuration |
| `ACZones.Manual`           | boolean          | Manual zone control mode |
| `ACZones.SlaveWallControls`| boolean          | Whether slave wall controllers are present |
| `ACZones.Zones`            | list[Zone]       | Zone definitions (may be empty) |
| `AOCFixed`                 | AOC              | Fixed add-on cooler config |
| `AOCInverter`              | AOC              | Inverter add-on cooler config |
| `Cabinets`                 | list[Cabinet]    | Physical cabinet info (serial, model, firmware) |
| `EVAPCooler`               | EVAPCoolerDef    | Evaporative cooler config |
| `WallController`           | WallControllerDef| Wall controller firmware and type |
| `Heater`                   | HeaterDef        | Heater config (model, serial, temperature range) |
| `MasterAirSensorPresent`   | boolean          | |
| `SlaveWallControls`        | integer          | Number of slave wall controllers |
| `NoOfZoneControls`         | integer          | Number of zone controls; 0 = single-zone system |
| `System`                   | SystemDef        | System configuration, device availability |
| `System.configuration`     | integer          | System configuration ID |
| `System.cooler`            | SystemDevice     | `{available: bool, fanFixed: bool}` |
| `System.heater`            | SystemDevice     | `{available: bool, fanFixed: bool}` |
| `System.fan`               | SystemDevice     | `{available: bool, fanFixed: bool}` |
| `System.Address`           | string           | Installation street address |
| `System.Name`              | string           | System name |
| `Wifi_Module`              | WifiModuleDef    | MAC address, firmware version, device type |
| `ExternalAirSensorPresent` | boolean          | |
| `DamperDelayModulePresent` | boolean          | |
| `BMSS1`                    | boolean          | Purpose unclear |
| `BMSMS1`                   | boolean          | Purpose unclear |
| `ZoneAirSensors`           | integer          | Number of zone air sensors |

---

## 6. State Lifecycle

### Reading State

1. Client authenticates via Cognito SRP (Section 1).
2. Client calls `GET /devices/system` to obtain `SystemDetails`, including the device MAC address (`Wifi_Module.MacAddressId`).
3. Client opens a WebSocket connection and sends a status request.
4. Server responds with multiple `RemoteStatus` messages. The first message with a non-empty `runningMode` and a new `timestamp` is treated as the initial state.
5. The WebSocket remains open. The server pushes state updates whenever the device state changes (e.g., temperature readings, physical button presses, zone damper changes).

### Sending Commands (Current Implementation)

The current implementation uses a full-state-overwrite pattern:

1. The client maintains a local copy of `RemoteStatus` (`current_state`).
2. To change a setting, the client mutates the local `current_state` optimistically (before confirmation).
3. The client serializes the entire `current_state` as the `params` of a command message.
4. The client sends the command over a new WebSocket connection.
5. The client waits for a response matching the expected change (via a `checker` callback).
6. If confirmed, the response is processed as the new state.
7. If not confirmed within the timeout, a background refresh is triggered to resync.

Source: `magiqtouch.py` lines 407-444, 533-697.

### State Update Processing

When a new `RemoteStatus` is received:

1. Each field is copied from the new state to the existing `current_state` object (in-place update).
2. For nested dataclasses (`fan`, `installed`), attributes are copied individually.
3. For list fields (`cooler`, `heater`), each unit is matched by index position, and the code validates that `zoneType` and `name` match between old and new entries.
4. The HA coordinator listener is notified to trigger entity updates.

Source: `structures.py` lines 443-461.

---

## 7. Known Quirks

### COMMON Zone `zoneOn` is Always Null

Devices with `zoneType: "COMMON"` always report `zoneOn: null`, never `true` or `false`. The system-level `systemOn` field controls whether the system is active. Individual zone on/off is only meaningful for `INDIVIDUAL` and `SLAVE` zone types.

Source: `develop/sequence/Log_1_Dul90.log` (COMMON zone entries), `magiqtouch.py` lines 548-553.

### Full State Commands Override Device Defaults

Because the current implementation sends the entire `RemoteStatus` on every command, it can override defaults that the device would otherwise apply. For example, when the device powers on via a physical button press, it may select specific default zones. If HA simultaneously sends a full state command (from a background refresh race or rapid toggle), the command's zone selection may override the device's power-on defaults.

This was observed in testing as HA "turning the heater back on" after the user turned it off via the physical controller.

Source: `develop/sequence/HA Testing Sequence.txt` lines 14, 35, 38.

### `touchCount` Field Purpose Unclear

The `touchCount` field is an integer that increments over time. It may represent a counter of physical interactions with the wall controller, or it may be a protocol-level sequence number. The client reads it but does not modify it in commands (it is included in the full state send because the entire state is serialized).

Observed values: 241, 528.

### Nullable Fields on SLAVE Zones

SLAVE zone `UnitDetails` entries have `null` for most configuration fields: `max_temp`, `min_temp`, `max_fan_speed`, `min_fan_speed`, `control_mode`, `programMode`, `ProgramModeOverridden`, `ProgramPeriodActive`, `programOverrideDisabled`. Only `zoneOn`, `set_temp`, `fan_speed`, `actual_temp`, `internal_temp`, and identity fields (`brand`, `name`, `zoneType`) are populated.

This means code reading these fields must handle `null` values (e.g., the HA climate entity's `max_temp` and `min_temp` properties can return `None` for slave zones).

Source: `develop/sequence/Log_1_Dul90.log` (SLAVE zone entries).

### Timestamp Units Inconsistency

The device reports `timestamp` values in milliseconds (e.g., `1710912802094`), but the client sets `timestamp` to seconds-precision UTC epoch when constructing commands (using `int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())`).

Source: `magiqtouch.py` lines 408-411.

### WebSocket Receives Multiple Messages After Status Request

After sending a status request, the server sends several `RemoteStatus` messages in rapid succession (5-6 observed within 1-2 seconds), then continues with periodic updates. All messages contain the same or very similar state. The purpose of the initial burst is unclear -- it may represent buffered state or multiple subsystem reports.

Source: `develop/sequence/Log_1_Dul90.log` lines 6-18.

### `runningMode` Values

| Value          | Meaning                        |
|----------------|--------------------------------|
| `"COOL"`       | Active cooling                 |
| `"COOLER_FAN"` | Cooler fan only (fresh air)    |
| `"HEAT"`       | Active heating                 |
| `"HEATER_FAN"` | Heater fan only (recirculate)  |

Source: `const.py` lines 28-33.

The `runningMode` persists even when `systemOn` is `false`. It indicates what mode the system was in (or will be in when turned on), not necessarily that the system is currently active.

### `runningState` / `zoneRunningState` Values

| Value               | Meaning                                |
|---------------------|----------------------------------------|
| `"NOT_REQUIRED"`    | Zone/unit is not actively running      |
| `"REQUIRED_RUNNING"`| Zone/unit is actively running          |

When switching modes, the client resets these to `"NOT_REQUIRED"` for all devices in the zone, then sets `"REQUIRED_RUNNING"` for the appropriate devices (coolers for cooling, heaters for heating).

Source: `magiqtouch.py` lines 581-648.

### `control_mode` Values

| Value    | Meaning                                    |
|----------|--------------------------------------------|
| `"TEMP"` | Temperature setpoint control               |
| `"FAN"`  | Manual fan speed control                   |
| `null`   | Not applicable (e.g., SLAVE zones, heater COMMON zones) |

Source: `const.py` lines 34-35.

### Old (Obsolete) Protocol

The codebase contains commented-out dataclass definitions (`RemoteStatusOld`, `SystemDetailsOld` in `structures.py` lines 50-233) representing an older flat-field protocol where zone data was encoded as numbered suffixes (e.g., `OnOffZone1`, `SetTempZone1`, ..., `SetTempZone10`). This older format used a different API endpoint and possibly MQTT instead of WebSocket.
