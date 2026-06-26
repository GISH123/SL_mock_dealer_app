"""
Tiny wrapper that:
  • maintains a reconnecting TCP stream,
  • feeds each full packet into MockDealerAppProtocol,
  • bubbles high-level events up to DragonTigerApp.
"""
import asyncio, struct, logging
from .protocol import MockDealerAppProtocol

HEADER_FMT = "!3I"
HEADER_LEN = struct.calcsize(HEADER_FMT)

log = logging.getLogger("DTClient")

class DealerTCPClient:
    def __init__(self, host, port, *, on_packet, on_disconnect,
                 reconnect_delay=3):
        self.host, self.port = host, port
        self.on_packet, self.on_disconnect = on_packet, on_disconnect
        self.reconnect_delay = reconnect_delay

    async def loop(self):
        while True:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("detector TCP error: %s – retrying in %ss",
                            e, self.reconnect_delay)
                self.on_disconnect()
                await asyncio.sleep(self.reconnect_delay)

    async def _run_once(self):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        proto = MockDealerAppProtocol(self.on_packet)
        while True:
            hdr = await reader.readexactly(HEADER_LEN)
            cmd, size, seq = struct.unpack(HEADER_FMT, hdr)
            body = await reader.readexactly(size-HEADER_LEN)
            proto.data_received(hdr+body)
