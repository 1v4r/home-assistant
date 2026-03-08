from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    ASSUME_FAHRENHEIT,
    BLE_CONNECT_TIMEOUT,
    BLE_PACKET_TIMEOUT,
    BLE_PROBE_TIMEOUT,
    COOKING_STATUS_OPTIONS,
    CTRL_CHAR_UUID,
    DATA_CHAR_UUID,
    PROBE_COUNT,
    SETTABLE_COOKING_STATUS,
    TIMER_SLOT_COUNT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ProbeReading:
    probe_id: int
    connected: bool
    temperature_raw: int | None
    temperature_c: float | None
    temperature_f: float | None
    cooking_status: int | None
    elapsed_seconds: int | None
    remaining_seconds: int | None


@dataclass(slots=True)
class A550Data:
    name: str
    address: str
    battery_percent: int | None
    probes: dict[int, ProbeReading]
    timers: dict[int, list[int]]


class A550Client:
    """Protocol client for the A550 BLE thermometer with persistent connection."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self._device_nonce: int | None = None
        self._token: bytes | None = None
        self._client: BleakClient | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._connect_lock = asyncio.Lock()
        self._poll_lock = asyncio.Lock()
        self._last_data = A550Data(
            name=name,
            address=address,
            battery_percent=None,
            probes={
                idx: ProbeReading(idx, False, None, None, None, None, None, None)
                for idx in range(PROBE_COUNT)
            },
            timers={idx: [0] * TIMER_SLOT_COUNT for idx in range(PROBE_COUNT)},
        )

    async def async_update(self) -> A550Data:
        async with self._poll_lock:
            await self._async_ensure_connected_and_initialized()

            battery_holder: dict[str, int | None] = {"value": self._last_data.battery_percent}
            probes: dict[int, ProbeReading] = {
                idx: self._last_data.probes.get(
                    idx,
                    ProbeReading(idx, False, None, None, None, None, None, None),
                )
                for idx in range(PROBE_COUNT)
            }
            timers: dict[int, list[int]] = {
                idx: list(self._last_data.timers.get(idx, [0] * TIMER_SLOT_COUNT))
                for idx in range(PROBE_COUNT)
            }

            client = self._client
            if client is None or not client.is_connected:
                raise UpdateFailed("A550 disconnected before polling")

            try:
                for probe_id in range(PROBE_COUNT):
                    await client.write_gatt_char(
                        CTRL_CHAR_UUID,
                        self._pkt_request_live_status(probe_id, self._device_nonce),
                        response=True,
                    )
                    await self._async_collect_probe_packets(
                        self._queue,
                        probes,
                        probe_id,
                        lambda batt: battery_holder.__setitem__("value", batt),
                    )

                for probe_id in range(PROBE_COUNT):
                    await client.write_gatt_char(
                        CTRL_CHAR_UUID,
                        self._pkt_request_timer_settings(probe_id, self._device_nonce),
                        response=True,
                    )
                    timers[probe_id] = await self._async_wait_for_timer_packet(self._queue, probe_id)
            except Exception as err:  # noqa: BLE001
                await self.async_disconnect()
                raise UpdateFailed(f"Failed to poll A550 at {self.address}: {err}") from err

            self._last_data = A550Data(
                name=self.name,
                address=self.address,
                battery_percent=battery_holder["value"],
                probes=probes,
                timers=timers,
            )
            return self._last_data

    async def async_set_cooking_status(self, probe_id: int, option: str) -> None:
        if option not in SETTABLE_COOKING_STATUS:
            raise UpdateFailed(f"Unsupported cooking status: {option}")
        async with self._poll_lock:
            await self._async_ensure_connected_and_initialized()
            client = self._client
            if client is None or not client.is_connected or self._device_nonce is None:
                raise UpdateFailed("A550 is not connected")
            await client.write_gatt_char(
                CTRL_CHAR_UUID,
                self._pkt_control_cooking(probe_id, SETTABLE_COOKING_STATUS[option], self._device_nonce),
                response=True,
            )
            await self._async_wait_for_packet(
                self._queue, lambda pkt: len(pkt) >= 5 and pkt[0] == 0x89 and pkt[1] == 0x05
            )

    async def async_set_timer_value(self, probe_id: int, slot: int, value: int) -> None:
        if probe_id not in range(PROBE_COUNT):
            raise UpdateFailed(f"Unsupported probe: {probe_id}")
        if slot not in range(TIMER_SLOT_COUNT):
            raise UpdateFailed(f"Unsupported timer slot: {slot}")
        if not 0 <= value <= 2047:
            raise UpdateFailed("Timer value must be between 0 and 2047")

        async with self._poll_lock:
            await self._async_ensure_connected_and_initialized()
            client = self._client
            if client is None or not client.is_connected or self._device_nonce is None:
                raise UpdateFailed("A550 is not connected")

            current = list(self._last_data.timers.get(probe_id, [0] * TIMER_SLOT_COUNT))
            if len(current) != TIMER_SLOT_COUNT:
                current = [0] * TIMER_SLOT_COUNT
            current[slot] = int(value)

            await client.write_gatt_char(
                CTRL_CHAR_UUID,
                self._pkt_set_timer(probe_id, TIMER_SLOT_COUNT, current, self._device_nonce),
                response=True,
            )
            await self._async_wait_for_packet(
                self._queue, lambda pkt: len(pkt) >= 5 and pkt[0] == 0x8B and pkt[1] == 0x05
            )
            self._last_data.timers[probe_id] = current

    async def _async_ensure_connected_and_initialized(self) -> None:
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return

            await self.async_disconnect()
            self._drain_queue()
            self._device_nonce = None
            self._token = None

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise UpdateFailed(f"Device {self.address} is not in Bluetooth range")

            def _notification_handler(_: int, data: bytearray) -> None:
                self._queue.put_nowait(bytes(data))

            try:
                client = BleakClient(ble_device, timeout=BLE_CONNECT_TIMEOUT)
                await client.connect()
                await client.start_notify(DATA_CHAR_UUID, _notification_handler)
                self._client = client
                await self._async_handshake(client, self._queue)
                _LOGGER.debug("Connected to A550 %s and completed handshake", self.address)
            except Exception as err:  # noqa: BLE001
                await self.async_disconnect()
                raise UpdateFailed(f"Failed to connect to A550 at {self.address}: {err}") from err

    async def async_disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            if client.is_connected:
                try:
                    await client.stop_notify(DATA_CHAR_UUID)
                except Exception:  # noqa: BLE001
                    pass
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self._drain_queue()

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _async_handshake(self, client: BleakClient, queue: asyncio.Queue[bytes]) -> None:
        await client.write_gatt_char(CTRL_CHAR_UUID, self._pkt_request_state(), response=True)
        state_pkt = await self._async_wait_for_packet(
            queue, lambda pkt: len(pkt) >= 6 and pkt[0] == 0x80 and pkt[1] == 0x06
        )
        self._device_nonce = state_pkt[4]

        await client.write_gatt_char(
            CTRL_CHAR_UUID,
            self._pkt_request_token(self._device_nonce),
            response=True,
        )
        token_pkt = await self._async_wait_for_packet(
            queue, lambda pkt: len(pkt) >= 10 and pkt[0] == 0x81 and pkt[1] == 0x0A
        )
        self._token = bytes(token_pkt[2:8])

        await client.write_gatt_char(
            CTRL_CHAR_UUID,
            self._pkt_verify_token(self._token, self._device_nonce),
            response=True,
        )
        await self._async_wait_for_packet(
            queue, lambda pkt: len(pkt) >= 5 and pkt[0] == 0x8C and pkt[1] == 0x05
        )

        await client.write_gatt_char(
            CTRL_CHAR_UUID,
            self._pkt_sync_clock(self._device_nonce),
            response=True,
        )
        await self._async_wait_for_packet(
            queue, lambda pkt: len(pkt) >= 5 and pkt[0] == 0x8A and pkt[1] == 0x05
        )

    async def _async_collect_probe_packets(
        self,
        queue: asyncio.Queue[bytes],
        probes: dict[int, ProbeReading],
        requested_probe_id: int,
        battery_callback: Callable[[int], None],
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + BLE_PROBE_TIMEOUT

        while loop.time() < deadline:
            timeout = max(0.05, deadline - loop.time())
            try:
                packet = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                return

            if not self._valid_checksum(packet):
                continue

            cmd = packet[0]
            length = packet[1]

            if cmd == 0xFF and length == 0x07 and len(packet) >= 7:
                probe_id = (packet[5] & 0xF0) >> 4
                if probe_id in probes:
                    probes[probe_id] = ProbeReading(probe_id, False, None, None, None, None, None, None)
                if probe_id == requested_probe_id:
                    return
                continue

            if cmd == 0x84 and length == 0x0C and len(packet) >= 12:
                probe_id, battery_percent, reading = self._parse_live_status(packet)
                battery_callback(battery_percent)
                if probe_id in probes:
                    probes[probe_id] = reading
                if probe_id == requested_probe_id:
                    return

    async def _async_wait_for_timer_packet(self, queue: asyncio.Queue[bytes], probe_id: int) -> list[int]:
        while True:
            packet = await self._async_wait_for_packet(
                queue,
                lambda pkt: len(pkt) >= 19 and pkt[0] == 0x83 and pkt[1] == 0x13,
            )
            pkt_probe, timers = self._parse_timer_settings(packet)
            if pkt_probe == probe_id:
                return timers

    async def _async_wait_for_packet(self, queue: asyncio.Queue[bytes], matcher: Callable[[bytes], bool]) -> bytes:
        while True:
            try:
                packet = await asyncio.wait_for(queue.get(), timeout=BLE_PACKET_TIMEOUT)
            except TimeoutError as err:
                raise UpdateFailed("Timed out waiting for BLE response") from err

            if not self._valid_checksum(packet):
                continue
            if matcher(packet):
                return packet

    @staticmethod
    def _valid_checksum(packet: bytes) -> bool:
        return len(packet) >= 2 and A550Client._xor_checksum(packet[:-1]) == packet[-1]

    @staticmethod
    def _xor_checksum(data: bytes) -> int:
        value = 0
        for byte in data:
            value ^= byte
        return value & 0xFF

    @staticmethod
    def _pkt_request_state() -> bytes:
        payload = bytes([0xA0, 0x04, 0x0F])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_request_token(nonce: int) -> bytes:
        payload = bytes([0xA1, 0x04, nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_verify_token(token: bytes, nonce: int) -> bytes:
        body = bytes([token[4], token[3], token[0], token[5], token[1], token[2], nonce & 0xFF])
        payload = bytes([0xAC, 0x0A]) + body
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_sync_clock(nonce: int) -> bytes:
        now = int(time.time()).to_bytes(4, "big")
        payload = bytes([0xAA, 0x08]) + now + bytes([nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_request_live_status(probe_id: int, nonce: int | None) -> bytes:
        if nonce is None:
            raise UpdateFailed("Missing device nonce")
        payload = bytes([0xA4, 0x05, probe_id & 0xFF, nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_request_timer_settings(probe_id: int, nonce: int | None) -> bytes:
        if nonce is None:
            raise UpdateFailed("Missing device nonce")
        payload = bytes([0xA3, 0x05, probe_id & 0xFF, nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _pkt_control_cooking(probe_id: int, status: int, nonce: int | None) -> bytes:
        if nonce is None:
            raise UpdateFailed("Missing device nonce")
        payload = bytes([0xA9, 0x06, probe_id & 0xFF, status & 0xFF, nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

    @staticmethod
    def _extract_bits(value: int, top: int, width: int, align_to: int = 7) -> int:
        bottom = top - width + 1
        mask = (1 << width) - 1
        out = (value >> bottom) & mask
        shift = align_to - top
        if shift > 0:
            out <<= shift
        elif shift < 0:
            out >>= -shift
        return out & 0xFF

    @staticmethod
    def _pkt_set_timer(probe_id: int, timer_count: int, timers: list[int], nonce: int | None) -> bytes:
        if nonce is None:
            raise UpdateFailed("Missing device nonce")
        vals = list(timers[:TIMER_SLOT_COUNT])
        vals += [0] * (TIMER_SLOT_COUNT - len(vals))
        payload = [0] * 19
        payload[0] = 0xAB
        payload[1] = 0x13
        payload[2] = ((probe_id & 0x0F) << 4) | (timer_count & 0x0F)
        payload[3] = A550Client._extract_bits(vals[0], 7, 8, 7)
        payload[4] = A550Client._extract_bits(vals[0], 10, 3, 7) | A550Client._extract_bits(vals[1], 5, 6, 4)
        payload[5] = A550Client._extract_bits(vals[1], 10, 6, 7) | A550Client._extract_bits(vals[2], 2, 3, 1)
        payload[6] = A550Client._extract_bits(vals[2], 9, 2, 7)
        payload[7] = A550Client._extract_bits(vals[2], 10, 1, 7) | A550Client._extract_bits(vals[3], 7, 8, 3)
        payload[8] = A550Client._extract_bits(vals[3], 10, 4, 7) | A550Client._extract_bits(vals[4], 4, 4, 3)
        payload[9] = A550Client._extract_bits(vals[4], 10, 7, 7) | A550Client._extract_bits(vals[5], 1, 1, 0)
        payload[10] = A550Client._extract_bits(vals[5], 8, 8, 7)
        payload[11] = A550Client._extract_bits(vals[5], 10, 2, 7) | A550Client._extract_bits(vals[6], 6, 7, 5)
        payload[12] = A550Client._extract_bits(vals[6], 10, 5, 7) | A550Client._extract_bits(vals[7], 3, 3, 2)
        payload[13] = A550Client._extract_bits(vals[7], 10, 8, 7)
        payload[14] = A550Client._extract_bits(vals[8], 8, 1, 7)
        payload[15] = A550Client._extract_bits(vals[8], 10, 3, 7) | A550Client._extract_bits(vals[9], 5, 6, 4)
        payload[16] = A550Client._extract_bits(vals[9], 10, 6, 7)
        payload[17] = nonce & 0xFF
        payload[18] = A550Client._xor_checksum(payload[:18])
        return bytes(payload)

    @staticmethod
    def _fahrenheit_to_celsius(temp_f: float) -> float:
        return (temp_f - 32.0) * 5.0 / 9.0

    @staticmethod
    def _parse_live_status(packet: bytes) -> tuple[int, int, ProbeReading]:
        battery_percent = packet[2] & 0x7F
        probe_id = (packet[3] >> 4) & 0x0F
        cooking_status = packet[3] & 0x0F
        elapsed_seconds = ((packet[8] & 0x1C) << 14) | (packet[5] << 8) | packet[4]
        remaining_seconds = ((packet[8] & 0xE0) << 11) | (packet[7] << 8) | packet[6]
        temp_raw = ((packet[9] << 2) | (packet[8] & 0x03)) - 100

        if temp_raw <= -50:
            return probe_id, battery_percent, ProbeReading(
                probe_id, False, None, None, None, cooking_status, elapsed_seconds, remaining_seconds
            )

        if ASSUME_FAHRENHEIT:
            temp_f = float(temp_raw)
            temp_c = round(A550Client._fahrenheit_to_celsius(temp_f), 1)
        else:
            temp_c = float(temp_raw)
            temp_f = round((temp_c * 9.0 / 5.0) + 32.0, 1)

        return probe_id, battery_percent, ProbeReading(
            probe_id, True, temp_raw, temp_c, temp_f, cooking_status, elapsed_seconds, remaining_seconds
        )

    @staticmethod
    def _parse_timer_settings(packet: bytes) -> tuple[int, list[int]]:
        timers = [0] * TIMER_SLOT_COUNT
        timers[0] = ((packet[3] & 0xE0) << 3) | packet[2]
        timers[1] = ((packet[4] & 0xFC) << 3) | (packet[3] & 0x1F)
        timers[2] = ((packet[6] & 0x80) << 3) | (packet[5] << 2) | (packet[4] & 0x03)
        timers[3] = ((packet[7] & 0xF0) << 3) | (packet[6] & 0x7F)
        timers[4] = ((packet[8] & 0xFE) << 3) | (packet[7] & 0x0F)
        timers[5] = ((packet[10] & 0xC0) << 3) | (packet[9] << 1) | (packet[8] & 0x01)
        timers[6] = ((packet[11] & 0xF8) << 3) | (packet[10] & 0x3F)
        timers[7] = (packet[12] << 3) | (packet[11] & 0x07)
        timers[8] = ((packet[14] & 0xE0) << 3) | packet[13]
        timers[9] = ((packet[15] & 0xFC) << 3) | (packet[14] & 0x1F)
        probe_id = (packet[16] >> 4) & 0x0F
        return probe_id, timers

    @staticmethod
    def cooking_status_name(code: int | None) -> str | None:
        if code is None:
            return None
        return COOKING_STATUS_OPTIONS.get(code, f"unknown_{code}")
