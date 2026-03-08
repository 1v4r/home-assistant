# A550 Home Assistant integration instructions

## Goal
Maintain and improve the Home Assistant custom integration for the A550 Bluetooth meat thermometer.

## Project constraints
- Preserve the persistent BLE connection behavior unless explicitly asked to change it.
- Avoid changes that would cause repeated reconnect beeps.
- Prefer small, testable changes over broad refactors.
- Keep entity IDs and user-facing names stable unless there is a strong reason to change them.
- Follow Home Assistant patterns where practical, but do not rewrite working protocol logic without a concrete benefit.

## BLE protocol summary
- Service UUID: `00006301-0000-0041-4c50-574953450000`
- Notify char: `00006302-0000-0041-4c50-574953450000`
- Write char: `00006303-0000-0041-4c50-574953450000`

### Handshake
1. Request state: `A0 04 0F AB`
2. Request token: `A1 04 <device_nonce> <chk>`
3. Verify token: `AC 0A ...`
4. Sync clock: `AA 08 ...`
5. Request live status: `A4 05 <probe_id> <device_nonce> <chk>`

## Known behavior
- The tested device appears to send probe temperatures in Fahrenheit.
- Home Assistant should handle display conversion based on its global Unit System.
- Error packets can arrive for missing probes; do not treat that as a fatal integration failure.
- Probe disconnects should map to unavailable, not bogus temperatures.

## Coding guidance
- Put protocol-specific comments near packet builders and parsers.
- Avoid adding new dependencies unless clearly necessary.
- If adding tests, start with deterministic packet encode/decode tests.
- Keep async BLE flows readable and conservative.

## Before major edits
Read:
- `docs/protocol.md`
- `docs/handover.md`
- `custom_components/a550/bluetooth.py`
- `custom_components/a550/coordinator.py`
