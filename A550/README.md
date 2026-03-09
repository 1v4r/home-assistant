## Wireless Meat Thermometer
Home Assistant Integration for the Model A550 Wireless Meat Thermometer by Clas Ohlson
Art.no 44-1794

## What it does

- discovers `GS_*` Bluetooth thermometers in Home Assistant
- connects actively over BLE
- performs the A550 handshake
- polls probe 0 and probe 1
- exposes three sensors:
  - Probe 0
  - Probe 1
  - Battery

## Install

Copy the files into your Home Assistant config directory:

```text
/config/custom_components/a550
```

Restart Home Assistant.

Then go to:

```text
Settings -> Devices & Services -> Add Integration -> A550
```

## Important note about units

Many A550 units appear to report live probe temperatures in Fahrenheit.
Home Assistant will automatically convert and display temperatures according to your configured Unit System (Metric or US Customary).

## Known limitations

- this first version only exposes probe 0, probe 1, and battery
- it polls rather than maintaining a long-lived session
- it does not yet expose cooking mode, timers, or history
- it does not yet include an options flow for unit selection


Update 2026-03-08: This build keeps the BLE connection open between polls to avoid the thermometer reconnect beep on every refresh.
