# Project handover

## What is working

- BLE discovery through Home Assistant
- Persistent BLE session
- Proprietary handshake
- Probe temperature polling
- Battery reporting
- Cooking status entity support
- Timer entity support
- Unit handling delegated to Home Assistant by exposing native units

## Known weak points

- Cooking status semantics are partially inferred from reverse-engineering.
- Timer slot semantics are still not fully mapped.
- There are no automated tests yet.
- Manifest documentation and issue tracker URLs are placeholders.
- Reconnect handling works, but could be made more robust if the device drops idle sessions.

## Good next improvements

1. Add parser / packet builder unit tests.
2. Confirm the exact semantics of timer slots 0-9.
3. Confirm the full cooking status enum and writable states.
4. Improve diagnostics and debug logging.
5. Add options flow only if real user need appears.
