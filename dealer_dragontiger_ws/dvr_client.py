import asyncio
import struct
import logging

log = logging.getLogger("DVR")

# ---------------------------------------------------------------------------
# DVR gateway–compatible packet layout (network byte order)
#   cmd:uint32 | size:uint32 | version:uint16 | table:4s | gmcode:16s
# PACKET_SIZE is always 30 bytes; VERSION = 1
# ---------------------------------------------------------------------------
PACKET_SIZE = 30
VERSION = 1

# Command IDs aligned with DVR_gateway
START_RECORD = 0x20001
STOP_RECORD  = 0x20002
START_PLACE  = 0x20003  # (not used by our app today)
STOP_PLACE   = 0x20004  # (not used)
KEEPALIVE    = 0x2000F  # (not used)

# "Header" and "body" lengths if you want to see a split in logs
_HDR_LEN  = 4 + 4 + 2     # cmd + size + version = 10
_BODY_LEN = 4 + 16        # table + gmcode      = 20
assert PACKET_SIZE == (_HDR_LEN + _BODY_LEN) == 30

# struct format for the whole frame
_PKT_FMT = "!IIH4s16s"


def _pad_table(table: str) -> bytes:
    """4-byte ASCII, null-padded."""
    return (table or "").encode("ascii", "ignore")[:4].ljust(4, b"\x00")


def _pad_gmcode(gmcode: str) -> bytes:
    """16-byte ASCII, null-padded."""
    return (gmcode or "").encode("ascii", "ignore")[:16].ljust(16, b"\x00")


def _hex_preview(b: bytes, limit=48) -> str:
    s = b[:limit].hex(" ")
    if len(b) > limit:
        s += " ..."
    return s


class DVRProtocol(asyncio.Protocol):
    """
    Minimal TCP client that sends a single 30-byte command frame per call.
    Matches DVR_gateway socket format: !IIH4s16s
    """
    def __init__(self):
        self.transport = None

    # asyncio.Protocol hooks ---------------------------------------------------
    def connection_made(self, transport):
        self.transport = transport
        peer = transport.get_extra_info("peername")
        log.info("[DVR] connected %s", peer)

    def connection_lost(self, exc):
        self.transport = None
        if exc:
            log.warning("[DVR] connection lost: %s", exc)
        else:
            log.info("[DVR] connection closed")

    def data_received(self, data: bytes):
        # If the DVR replies, you'll see it here (DEBUG shows hex)
        log.debug("[DVR] recv %d bytes: %s", len(data), _hex_preview(data))

    # API used by main.py ------------------------------------------------------
    def send_dvr_command(self, cmd: int, *, table: str, gmcode: str):
        """
        Send a DVR command using the gateway's 30-byte format.
        Functionality of the rest of the app remains unchanged.
        """
        if self.transport is None:
            raise RuntimeError("DVR not connected")

        tbl = _pad_table(table)
        gmc = _pad_gmcode(gmcode)

        pkt = struct.pack(_PKT_FMT, cmd, PACKET_SIZE, VERSION, tbl, gmc)

        # Log precise sizes and a short hex preview
        log.info(
            "[DVR->Server] cmd=0x%05X size=%d (hdr=%d body=%d) version=%d table=%s gm=%s",
            cmd, len(pkt), _HDR_LEN, _BODY_LEN, VERSION, table, gmcode
        )
        log.debug("[DVR] packet: %s", _hex_preview(pkt))

        self.transport.write(pkt)


# ---------------------------------------------------------------------------

async def _connect_async(host: str, port: int, loop):
    transport, proto = await loop.create_connection(DVRProtocol, host, port)
    return proto

def connect_to_dvr(host: str, port: int, *, loop=None) -> DVRProtocol:
    loop = loop or asyncio.get_event_loop()
    if loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(_connect_async(host, port, loop), loop)
        return fut.result()
    else:
        return loop.run_until_complete(_connect_async(host, port, loop))
