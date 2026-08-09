# EWPE Smart — Home Assistant Integration

**Date:** 2026-04-28
**Status:** Approved (informal — user requested execution without formal review)
**Author:** Tomas Marek

## Problem

The user owns Daitsu commercial cassette air conditioners with WiFi controllers
that communicate via the EWPE Smart mobile app. The official Home Assistant
`gree` integration fails to discover these units (likely due to broadcast
behaviour / network topology). The user has the IP addresses of both controllers
and wants a Home Assistant integration that allows local control of these units
without requiring an MQTT broker or external bridge process.

## Scope (Phase 1)

In scope:

- Local Python `custom_component` for Home Assistant
- Manual host/IP configuration (primary path) and best-effort UDP broadcast
  discovery (secondary path)
- Per-device config entry (multi-device support)
- `climate` entity exposing: power on/off, HVAC mode (Auto / Cool / Heat / Dry /
  Fan only), target temperature, fan speed (Auto / Low / Medium / High), current
  indoor temperature
- Polling every 30 seconds (configurable via Options Flow)
- Reauth flow when device key becomes invalid
- Unit tests for protocol, device, config flow, and climate entity

Out of scope (deferred):

- Vertical and horizontal swing controls
- Switch entities for Sleep / Turbo / X-Fan / Health / Display light / etc.
- Frost protection (8 °C heating)
- Air purifier / dehumidifier device classes
- HACS submission to default repository (user will install via custom HACS repo
  or manually)

## Architecture

### Layer separation

The integration is split into five layers, with strict dependency direction
top → bottom:

| Layer | Module | Imports `homeassistant.*`? | Responsibility |
|-------|--------|---------------------------|----------------|
| 1. Protocol | `protocol.py` | No | AES-128 ECB encrypt/decrypt; UDP send/receive helpers; packet builders |
| 2. Device | `device.py` | No | `EwpeDevice` class — bind handshake, status read, command write |
| 3. Coordinator | `coordinator.py` | Yes | `DataUpdateCoordinator` polling loop |
| 4. Config | `config_flow.py` | Yes | User flow, options flow, reauth flow |
| 5. Entities | `climate.py`, `sensor.py` | Yes | Map coordinator data to HA entities |

Layers 1–2 are HA-free, allowing them to be tested as a plain Python library
with a mock UDP server.

### Protocol summary

Source: reverse-engineered protocol from `tomikaa87/gree-remote`, also used by
`stas-demydiuk/ewpe-smart-mqtt`.

- Transport: UDP, default port 7000
- Encryption: AES-128 ECB with PKCS#7 padding, base64-encoded
- Generic key (used for scan and bind only): `a3K8Bx%2r8Y7#xDh`
- Each device returns a unique 16-byte key during bind handshake; subsequent
  status/cmd packets are encrypted with this device-specific key
- Outer packet: `{"cid": "app", "i": 0|1, "t": "pack", "uid": 0, "pack": "<base64>"}`
  - `i: 1` when using generic key (scan, bind), `i: 0` when using device key
- Inner (encrypted) packet types:
  - `scan` (broadcast, no encryption needed) → device responds with `dev`
  - `bind` (generic key) → device responds with `bindok` containing `key`
  - `status` (device key) → device responds with `dat` containing `cols`/`dat`
  - `cmd` (device key) → device responds with `res` containing `opt`/`val`

### Status keys (Phase 1)

| Key | Meaning | Range |
|-----|---------|-------|
| `Pow` | Power | 0=off, 1=on |
| `Mod` | HVAC mode | 0=Auto, 1=Cool, 2=Dry, 3=Fan, 4=Heat |
| `SetTem` | Target temperature | 16–30 °C |
| `TemUn` | Temperature unit | 0=°C, 1=°F |
| `WdSpd` | Fan speed | 0=Auto, 1=Low, 3=Medium, 5=High |
| `TemSen` | Indoor temperature sensor | raw value, offset by -40 °C |

### File layout

```
ewpe-smart-ha/
├── custom_components/ewpe_smart/
│   ├── __init__.py
│   ├── manifest.json
│   ├── const.py
│   ├── protocol.py
│   ├── device.py
│   ├── coordinator.py
│   ├── config_flow.py
│   ├── climate.py
│   ├── sensor.py
│   ├── strings.json
│   └── translations/
│       ├── en.json
│       └── cs.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── mock_device.py
│   ├── test_protocol.py
│   ├── test_device.py
│   ├── test_config_flow.py
│   └── test_climate.py
├── docs/superpowers/specs/...
├── hacs.json
├── manifest.json (HACS)
├── pyproject.toml
├── requirements_test.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Component design

### `EwpeProtocol` (protocol.py)

Pure async helpers, no class state:

- `encrypt(payload: dict, key: bytes) -> str`
- `decrypt(ciphertext: str, key: bytes) -> dict`
- `async send_request(host, port, key, payload, timeout) -> dict` — opens an
  ephemeral UDP socket, sends the encrypted outer packet, awaits the matching
  reply, decrypts and returns the inner payload
- `async scan(broadcast_addr, timeout) -> list[dict]` — broadcasts a scan
  packet, collects all `dev` replies for the timeout duration

### `EwpeDevice` (device.py)

```python
class EwpeDevice:
    host: str
    port: int = 7000
    mac: str | None
    name: str | None
    key: bytes | None  # device-specific key, set after bind()

    async def bind(self) -> None
    async def get_status(self, cols: list[str] | None = None) -> dict
    async def set_state(self, params: dict[str, int]) -> dict
```

`bind()` discovers the device on its own IP (sends a scan packet to host) to
learn the MAC, then performs the bind handshake. If `mac` is already known
(from previous config entry), `bind()` skips scan and goes straight to bind.

### `EwpeCoordinator` (coordinator.py)

Standard `DataUpdateCoordinator`:

- Polls `device.get_status()` at the configured interval
- On `EwpeError`, raises `UpdateFailed` to put the entity into "unavailable"
- On `EwpeAuthError` (decrypt failure with stored key), raises
  `ConfigEntryAuthFailed` to trigger reauth flow

### Config flow (config_flow.py)

Step `user`:

1. Show form: `host` (required), `name` (optional)
2. On submit: instantiate `EwpeDevice(host)`, call `bind()`
3. On success: set unique_id = MAC, abort if already configured, create entry
   with `{host, port, mac, key, name}`
4. On timeout / decrypt failure: show error in form

Discovery step (optional, run from a separate menu option):

1. Broadcast scan on user-supplied network (default `255.255.255.255`)
2. Show found devices in a select dropdown
3. Selecting an entry pre-fills the user step

Reauth step:

- Triggered when stored device key fails to decrypt a status reply
- Asks user to power-cycle the device, then re-runs bind

Options flow:

- Single field: `update_interval` (10–300 seconds, default 30)

### Entities

**`EwpeClimateEntity`** — main climate device:

- `_attr_hvac_modes = [OFF, AUTO, COOL, DRY, FAN_ONLY, HEAT]`
- `_attr_fan_modes = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]`
- `_attr_supported_features = TARGET_TEMPERATURE | FAN_MODE | TURN_ON | TURN_OFF`
- `_attr_min_temp = 16`, `_attr_max_temp = 30`
- `_attr_target_temperature_step = 1`
- `_attr_temperature_unit = UnitOfTemperature.CELSIUS`
- Reads coordinator data, maps `Pow`/`Mod` → `hvac_mode`, `WdSpd` → `fan_mode`,
  `SetTem` → `target_temperature`, `TemSen + offset` → `current_temperature`
- Writes via `device.set_state({...})` then triggers coordinator refresh

**`EwpeIndoorTemperatureSensor`** — separate sensor entity for graphing:

- `device_class = TEMPERATURE`, `state_class = MEASUREMENT`
- Native value = `TemSen + offset` (clamped to plausible range)

## Error handling

| Condition | Where caught | User-visible behaviour |
|-----------|--------------|------------------------|
| UDP timeout (5 s) | `protocol.send_request` | `EwpeTimeout` → coordinator marks unavailable |
| Bad decrypt with stored key | `device.get_status` | `EwpeAuthError` → reauth flow |
| Bad JSON / wrong response type | `protocol.send_request` | `EwpeProtocolError` → unavailable |
| `host` unreachable | OS error → `EwpeTimeout` | unavailable |
| Bind timeout in config flow | `config_flow` | error shown inline |
| Duplicate device (same MAC) | `config_flow` | abort with `already_configured` |

Coordinator backoff is handled by HA core (built into `DataUpdateCoordinator`).

## Testing strategy

Tests use `pytest-homeassistant-custom-component` for HA-aware tests and a
local UDP mock server (`tests/mock_device.py`) that simulates a real device by:

- Listening on 127.0.0.1 with an ephemeral port
- Decrypting incoming packets with the appropriate key
- Responding with realistic `bindok` / `dat` / `res` packets

Test files:

| File | What it tests |
|------|--------------|
| `test_protocol.py` | encrypt/decrypt round-trip; PKCS#7 padding correctness |
| `test_device.py` | bind handshake, status read, set_state, timeout, bad decrypt → exception |
| `test_config_flow.py` | user flow happy path, error paths (cannot_connect, already_configured), options flow |
| `test_climate.py` | mode mapping (Pow=0 → OFF, Pow=1 + Mod=1 → COOL, etc.); set_temperature → coordinator.device.set_state called with `SetTem` |

CI is not in scope for Phase 1 (the user can add GitHub Actions later); tests
are meant to be runnable locally with `pytest` after `pip install -r
requirements_test.txt`.

## Installation paths (deliverable in README)

1. **Manual**: clone the repo, copy `custom_components/ewpe_smart/` into the
   user's HA `config/custom_components/`, restart HA, add integration via UI.
2. **HACS custom repository**: user adds the GitHub URL to HACS as a custom
   repository with category "Integration", installs from HACS UI.

The README must list both with screenshots of where to click in the HA UI
described in text form.

## Open questions / future work

- Add switch entities for sleep/turbo/x-fan/health/display light when the user
  asks for them (Phase 2)
- Add vertical swing control through `SwUpDn` (Phase 3)
- Add optional horizontal swing through `SwingLfRig` when needed; protocol
  support does not prove that a left/right motor is installed
- Submit upstream to HACS default repository once stable
- Possibly contribute manual-host support upstream to HA core `gree`
  integration as a future improvement
