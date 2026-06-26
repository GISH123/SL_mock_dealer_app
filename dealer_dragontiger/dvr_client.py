import asyncio, struct, logging
log = logging.getLogger("DVR")

_HEADER_FMT = "!3I"
_HEADER_LEN = struct.calcsize(_HEADER_FMT)

START_RECORD  = 0x100001
STOP_RECORD   = 0x100002

class DVRProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.seq = 0

    def connection_made(self, t):
        self.transport = t

    def connection_lost(self, exc):
        self.transport = None

    def send_dvr_command(self, cmd: int, *, table: str, gmcode: str):
        if not self.transport:
            raise RuntimeError("DVR not connected")
        tbl = table.encode("ascii").ljust(14, b"\x00")
        gm  = gmcode.encode("ascii").ljust(14, b"\x00")
        body = struct.pack("!14s14sH", tbl, gm, 0)
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
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
