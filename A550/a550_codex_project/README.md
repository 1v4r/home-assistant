# A550 Home Assistant integration

Custom Home Assistant integration for the Clas Ohlson / Grill Smart A550 Bluetooth meat thermometer.

## Current status

This repo contains a working custom integration that:

- discovers `GS_*` A550 devices through Home Assistant Bluetooth
- keeps a persistent BLE connection open to avoid the device beeping on every poll
- performs the proprietary A550 handshake
- reads battery and probe temperatures
- exposes cooking status controls and timer controls
- reports temperatures to Home Assistant using the device's native unit so HA can apply its own Unit System setting

## Repository layout

- `custom_components/a550/` – integration code
- `docs/protocol.md` – reverse-engineered BLE protocol notes
- `docs/handover.md` – project handover summary and known risks
- `AGENTS.md` – Codex instructions for this repo
- `prompts/codex-start.txt` – a good first prompt for Codex

## Install in Home Assistant

Copy `custom_components/a550` into your HA config directory:

```text
/config/custom_components/a550
```

Restart Home Assistant, then add the integration from:

```text
Settings -> Devices & Services -> Add Integration -> A550
```

## Development notes

The integration is intentionally based on an active BLE connection. The device beeps on connect, so reconnect frequency is a user-visible behavior and must be treated carefully.

The code currently assumes the device emits Fahrenheit natively:

```python
ASSUME_FAHRENHEIT = True
```

This reflects current reverse-engineering results for the tested unit. Home Assistant then converts for display based on the user's global Unit System.

## Suggested next tasks

- Verify and refine cooking status mappings
- Verify the meaning of all 10 timer slots
- Add better reconnect / stale-session recovery
- Add tests for packet builders and parsers
- Replace placeholder manifest documentation links with the real repo URL
