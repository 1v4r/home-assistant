# A550 BLE protocol notes

These notes summarize the reverse-engineered BLE protocol used by the A550 / Grill Smart thermometer.

## BLE layout

- Device local name: `GS_<id>`
- Service: `00006301-0000-0041-4c50-574953450000`
- Notify characteristic: `00006302-0000-0041-4c50-574953450000`
- Write characteristic: `00006303-0000-0041-4c50-574953450000`

## Request packets

### Request device state

```text
A0 04 0F AB
```

### Request token

```text
A1 04 <device_nonce> <chk>
```

### Verify token

```text
AC 0A t4 t3 t0 t5 t1 t2 <device_nonce> <chk>
```

The 6-byte token is reordered before sending:

```text
[4], [3], [0], [5], [1], [2]
```

### Sync clock

```text
AA 08 <unix_time_be_4_bytes> <device_nonce> <chk>
```

### Request live status

```text
A4 05 <probe_id> <device_nonce> <chk>
```

## Reply packets

### Reply device state

```text
80 06 <state> <app_nonce> <device_nonce> <chk>
```

### Reply app registration / token

```text
81 0A <6 token bytes> <device_nonce> <chk>
```

### Verify token ack

```text
8C 05 <ack> <device_nonce> <chk>
```

### Sync clock ack

```text
8A 05 <ack> <device_nonce> <chk>
```

### Live status

```text
84 0C ...
```

Fields parsed from current implementation:

- battery percent
- probe id
- cooking status
- elapsed time
- remaining time
- current temperature
- device nonce

On the tested unit, the raw current temperature behaves like Fahrenheit. Home Assistant should convert for display based on its own unit system.

### Error packet

```text
FF 07 <error_code> <sub_error> <reply_cmd> <probe nibble> <chk>
```

These appear when querying probes that are not connected.

## Notes

- Keeping a persistent BLE connection avoids repeated audible beeps on the device.
- Reconnect behavior is user-visible and should be treated as part of the UX.
