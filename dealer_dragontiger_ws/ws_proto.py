import asyncio
import os
import struct
import logging
import websockets

log = logging.getLogger("DTWS")

CMD_LOGIN_R_D2C       = 0xBA0002
CMD_START_PREDICT_D2C = 0xBA0003
CMD_STOP_PREDICT_D2C  = 0xBA0004
CMD_DISPATCH_IDX_D2C  = 0xBA0006
CMD_SAVE_RESULT_D2C   = 0xBA0007

CMD_KEEPALIVE      = 0xAB0001
CMD_PREDICT_RESULT = 0xAB0004

_HEADER_FMT = "!3I"
_HEADER_LEN = struct.calcsize(_HEADER_FMT)


def _resolve_ws_uri() -> str:
    def _clean(s: str) -> str:
        return s.strip().strip('"').strip("'")
    uri = os.getenv("WS_URI")
    if uri and uri.strip():
        return _clean(uri)
    host = os.getenv("WS_HOST")
    port = os.getenv("WS_PORT")
    if host and port:
        return f"ws://{_clean(host)}:{_clean(port)}"
    return "ws://10.146.11.214:3331"


class WSDealerProto:
    def __init__(self, app):
        self.app = app
        self.ws = None
        self.seq = 0
        self.logged_in = False
        self.uri = None

    async def connect(self):
        self.uri = _resolve_ws_uri()
        self.ws = await websockets.connect(self.uri)
        self.app.proto_ws = self
        self.logged_in = True
        self.app.gui.set_status(f"WS connected, {self.uri} , waiting for LOGIN…", color="orange")
        await self._send_login_r()
        asyncio.create_task(self._recv_loop())

    async def _recv_loop(self):
        async for raw in self.ws:
            self._handle_raw(raw)

    def _handle_raw(self, data: bytes):
        off = 0
        while off + _HEADER_LEN <= len(data):
            cmd, size, seq = struct.unpack_from(_HEADER_FMT, data, off)
            pkt_len = _HEADER_LEN + (size - _HEADER_LEN)
            if off + pkt_len > len(data):
                break
            body = data[off + _HEADER_LEN : off + pkt_len]

            if cmd == CMD_PREDICT_RESULT:
                self._handle_prediction(body)
            off += pkt_len

    def _handle_prediction(self, body: bytes):
        # Only accept predict results during an active round
        if not getattr(self.app, 'predicting', False):
            return

        self.app.gui.on_first_result()
        if len(body) < 16:
            return
        gmcode_bytes, cnt = struct.unpack_from('!14sh', body, 0)
        off = 16
        for _ in range(cnt):
            idx, card_val, score = struct.unpack_from('!2hd', body, off)
            off += struct.calcsize('!2hd')
            if hasattr(self.app, 'on_predict_result'):
                self.app.on_predict_result(idx, card_val, score, gmcode_bytes=gmcode_bytes)
            else:
                self.app.gui.update_card(idx, card_val)

    async def _send_login_r(self):
        body = struct.pack("!I4s4s", 0, b"DT", b"B021")
        await self._send(CMD_LOGIN_R_D2C, body)
        self.app.gui.set_status(f"Detector ready (WS) : {self.uri}", color="green")
        self.app.gui.enable_start_prediction()

    async def send_start_predict(self, gmcode: str):
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14, b"\x00"), 2)
        await self._send(CMD_START_PREDICT_D2C, body)

    async def send_stop_predict(self, gmcode: str):
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14, b"\x00"), 0)
        await self._send(CMD_STOP_PREDICT_D2C, body)

    async def send_dispatch_index(self, gmcode: str, idx: int):
        gm14 = gmcode.encode("ascii")[:14].ljust(14, b"\x00")
        body = struct.pack("!14sh", gm14, idx)
        await self._send(CMD_DISPATCH_IDX_D2C, body)

    async def send_save_result(self, gmcode: str):
        gm_bytes = gmcode.encode("ascii", "ignore")[:14].ljust(14, b"\x00")
        body = struct.pack("!14s", gm_bytes)
        await self._send(CMD_SAVE_RESULT_D2C, body)

    async def _send(self, cmd: int, body: bytes = b""):
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
        # 📏 log packet length when sending
        log.info("[WS->Detector]  cmd=0x%06X size=%d (hdr=%d body=%d) seq=%d",
                 cmd, len(pkt), _HEADER_LEN, len(pkt) - _HEADER_LEN, self.seq)
        await self.ws.send(pkt)
