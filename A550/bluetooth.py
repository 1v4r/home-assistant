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
    SETTABLE_COOKING_STATUS
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
            except Exception as err:  # noqa: BLE001
                await self.async_disconnect()
                raise UpdateFailed(f"Failed to poll A550 at {self.address}: {err}") from err

            self._last_data = A550Data(
                name=self.name,
                address=self.address,
                battery_percent=battery_holder["value"],
                probes=probes,
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
    def _pkt_control_cooking(probe_id: int, status: int, nonce: int | None) -> bytes:
        if nonce is None:
            raise UpdateFailed("Missing device nonce")
        payload = bytes([0xA9, 0x06, probe_id & 0xFF, status & 0xFF, nonce & 0xFF])
        return payload + bytes([A550Client._xor_checksum(payload)])

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