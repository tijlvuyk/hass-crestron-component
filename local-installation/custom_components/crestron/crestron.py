import asyncio
import struct
import logging
from contextlib import suppress

_LOGGER = logging.getLogger(__name__)


class CrestronXsig:
    def __init__(self):
        self._digital = {}
        self._analog = {}
        self._serial = {}
        self._writer = None
        self._callbacks = set()
        self._server = None
        self._server_task = None
        self._available = False
        self._sync_all_joins_callback = None

    async def listen(self, port):
        server = await asyncio.start_server(
            self.handle_connection,
            "0.0.0.0",
            port,
        )

        self._server = server
        addr = server.sockets[0].getsockname()
        _LOGGER.info(f"Listening on {addr}")

        self._server_task = asyncio.create_task(server.serve_forever())

    async def stop(self):
        self._available = False
        for callback in tuple(self._callbacks):
            await callback("available", "False")

        _LOGGER.info("Stop called. Closing connection")

        if self._writer:
            self._writer.close()
            with suppress(ConnectionError):
                await self._writer.wait_closed()
            self._writer = None

        if self._server_task is not None:
            self._server_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._server_task
            self._server_task = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def register_sync_all_joins_callback(self, callback):
        self._sync_all_joins_callback = callback

    def register_callback(self, callback):
        self._callbacks.add(callback)

    def remove_callback(self, callback):
        self._callbacks.discard(callback)

    async def handle_connection(self, reader, writer):
        """Handle Crestron connection safely"""
        peer = writer.get_extra_info("peername")
        _LOGGER.info(f"Control system connection from {peer}")

        if self._writer is not None and self._writer is not writer:
            _LOGGER.info("Closing previous control system connection")
            self._writer.close()
            with suppress(ConnectionError):
                await self._writer.wait_closed()

        self._writer = writer
        self._available = True

        # notify HA
        for callback in tuple(self._callbacks):
            await callback("available", "True")

        try:
            writer.write(b"\xfd")  # request sync

            while True:
                try:
                    data = await reader.readexactly(1)
                except asyncio.IncompleteReadError:
                    _LOGGER.info("Crestron disconnected (clean)")
                    break
                except OSError as e:
                    _LOGGER.warning(f"Socket read error: {e}")
                    break

                # Sync request
                if data[0] == 0xFB:
                    if self._sync_all_joins_callback:
                        await self._sync_all_joins_callback()
                    continue

                # read second byte safely
                try:
                    data += await reader.readexactly(1)
                except Exception:
                    break

                # Digital
                if (
                    data[0] & 0b11000000 == 0b10000000
                    and data[1] & 0b10000000 == 0b00000000
                ):
                    header = struct.unpack("BB", data)
                    join = ((header[0] & 0b00011111) << 7 | header[1]) + 1
                    value = ~header[0] >> 5 & 0b1

                    self._digital[join] = bool(value)

                    for callback in tuple(self._callbacks):
                        await callback(f"d{join}", str(value))

                # Analog
                elif (
                    data[0] & 0b11001000 == 0b11000000
                    and data[1] & 0b10000000 == 0b00000000
                ):
                    try:
                        data += await reader.readexactly(2)
                    except Exception:
                        break

                    header = struct.unpack("BBBB", data)
                    join = ((header[0] & 0b00000111) << 7 | header[1]) + 1
                    value = (
                        (header[0] & 0b00110000) << 10
                        | header[2] << 7
                        | header[3]
                    )

                    self._analog[join] = value

                    for callback in tuple(self._callbacks):
                        await callback(f"a{join}", str(value))

                # Serial
                elif (
                    data[0] & 0b11111000 == 0b11001000
                    and data[1] & 0b10000000 == 0b00000000
                ):
                    try:
                        payload = await reader.readuntil(b"\xff")
                    except Exception:
                        break

                    header = struct.unpack("BB", data[:2])
                    join = ((header[0] & 0b00000111) << 7 | header[1]) + 1
                    string = payload[:-1].decode("utf-8", errors="ignore")

                    self._serial[join] = string

                    for callback in tuple(self._callbacks):
                        await callback(f"s{join}", string)

                else:
                    _LOGGER.debug(f"Unknown Packet: {data.hex()}")

        except Exception as e:
            _LOGGER.warning(f"Connection handler crashed: {e}")

        finally:
            _LOGGER.info("Cleaning up connection")

            self._available = False
            if self._writer is writer:
                self._writer = None

            for callback in tuple(self._callbacks):
                await callback("available", "False")

            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    def is_available(self):
        return self._available

    def get_analog(self, join):
        return self._analog.get(join, 0)

    def get_digital(self, join):
        return self._digital.get(join, False)

    def get_serial(self, join):
        return self._serial.get(join, "")

    def _safe_write(self, data):
        """Safe write wrapper to avoid socket.send errors"""
        if not self._writer:
            _LOGGER.debug("Write skipped: no connection")
            return

        try:
            self._writer.write(data)
        except Exception as e:
            _LOGGER.warning(f"Write failed, dropping connection: {e}")
            self._writer = None
            self._available = False

    def set_analog(self, join, value):
        data = struct.pack(
            ">BBBB",
            0b11000000 | (value >> 10 & 0b00110000) | (join - 1) >> 7,
            (join - 1) & 0b01111111,
            value >> 7 & 0b01111111,
            value & 0b01111111,
        )
        self._safe_write(data)

    def set_digital(self, join, value):
        bit = 0 if value else 1
        data = struct.pack(
            ">BB",
            0b10000000 | (bit << 5) | (join - 1) >> 7,
            (join - 1) & 0b01111111,
        )
        self._safe_write(data)

    def set_serial(self, join, string):
        if len(string) > 252:
            _LOGGER.warning(f"String too long ({len(string)})")
            return

        data = struct.pack(
            ">BB", 0b11001000 | ((join - 1) >> 7), (join - 1) & 0b01111111
        )
        data += string.encode()
        data += b"\xff"

        self._safe_write(data)
