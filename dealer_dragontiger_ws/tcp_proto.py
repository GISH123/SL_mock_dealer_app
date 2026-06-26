import asyncio, struct, logging
log = logging.getLogger("DTProto")

CMD_LOGIN_R_D2C       = 0xBA0002
CMD_START_PREDICT_D2C = 0xBA0003
CMD_STOP_PREDICT_D2C  = 0xBA0004
CMD_DISPATCH_IDX_D2C  = 0xBA0006
CMD_SAVE_RESULT_D2C   = 0xBA0007

CMD_KEEPALIVE      = 0xAB0001
CMD_LOGIN          = 0xAB0002
CMD_PREDICT_RESULT = 0xAB0004

_HEADER_FMT = "!3I"; _HEADER_LEN = struct.calcsize(_HEADER_FMT)

class MockDealerAppProtocol(asyncio.Protocol):
    def __init__(self, app):
        self.app = app
        self.transport = None
        self.seq = 0
        self.logged_in = False
        self.login_sent = False
        self.svrid = b"1001"
        # TCP is stream-based; packets can arrive split/coalesced.
        # Keep an internal buffer to avoid mis-parsing partial packets.
        self._buf = bytearray()

    def connection_made(self, transport):
        self.transport = transport
        self.app.proto_tcp = self
        self.logged_in = False
        self.app.gui.set_status("TCP connected, waiting for LOGIN…", color="orange")
        self.app.gui.disable_save_result()

    def connection_lost(self, exc):
        self.transport = None
        self.app.proto_tcp = None
        self.logged_in = False
        self._buf.clear()
        self.app.gui.set_status("Detector disconnected.", color="red")
        self.app.gui.disable_start_prediction()
        self.app.gui.disable_stop_prediction()
        self.app.gui.disable_dispatch_buttons()
        self.app.gui.disable_save_result()

    def data_received(self, data: bytes):
        # TCP is a stream: packets can be split/coalesced. Buffer and parse by size field.
        self._buf += data
        while True:
            if len(self._buf) < _HEADER_LEN:
                return
            cmd, size, seq = struct.unpack_from(_HEADER_FMT, self._buf, 0)
            if size < _HEADER_LEN:
                # Desync guard: drop one byte and retry
                self._buf = self._buf[1:]
                continue
            if len(self._buf) < size:
                return
            pkt = self._buf[:size]
            self._buf = self._buf[size:]

            # handle packet
            if cmd == CMD_LOGIN:
                self._send_login_reply()
                continue
            if cmd == CMD_PREDICT_RESULT:
                body = pkt[_HEADER_LEN:]
                self._handle_prediction(body)
                continue

            # ignore others

    # sends
    def send_start_predict(self, gmcode: str):
        if not self.logged_in: return
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14,b"\x00"), 2)
        self._send(CMD_START_PREDICT_D2C, body)
    def send_stop_predict(self, gmcode: str):
        if not self.logged_in: return
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14,b"\x00"), 0)
        self._send(CMD_STOP_PREDICT_D2C, body)
    def send_dispatch_index(self, gmcode: str, idx: int):
        if not self.logged_in: return
        gm14 = gmcode.encode("ascii")[:14].ljust(14,b"\x00")
        body = struct.pack("!14sh", gm14, idx)
        self._send(CMD_DISPATCH_IDX_D2C, body)
    def send_save_result(self, gmcode: str):
        if not self.logged_in: return
        gm_bytes = gmcode.encode("ascii","ignore")[:14].ljust(14,b"\x00")
        body = struct.pack("!14s", gm_bytes)
        self._send(CMD_SAVE_RESULT_D2C, body)

    # internals
    def _send_login_reply(self):
        if self.login_sent: return
        self.login_sent = True
        self.logged_in  = True
        body = struct.pack("!I4s4s", 0, b"DT", self.svrid)
        self._send(CMD_LOGIN_R_D2C, body)
        self.app.gui.set_status("Detector ready (TCP).", color="green")
        self.app.gui.enable_start_prediction()

    def _handle_prediction(self, body: bytes):
        # Only accept predict results during an active round
        if not getattr(self.app, 'predicting', False):
            return

        self.app.gui.on_first_result()

        if len(body) < struct.calcsize('!14sh'):
            return
        gmcode_bytes, count = struct.unpack_from('!14sh', body, 0)
        off = struct.calcsize('!14sh')
        for _ in range(count):
            if len(body) < off + struct.calcsize('!2hd'):
                return
            idx, dealer_val, score = struct.unpack_from('!2hd', body, off)
            off += struct.calcsize('!2hd')
            if hasattr(self.app, 'on_predict_result'):
                self.app.on_predict_result(idx, dealer_val, score, gmcode_bytes=gmcode_bytes)
            else:
                self.app.gui.update_card(idx, dealer_val)

    def _send(self, cmd: int, body: bytes = b""):
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
        # 📏 log packet length when sending
        log.info("[TCP->Detector] cmd=0x%06X size=%d (hdr=%d body=%d) seq=%d",
                 cmd, len(pkt), _HEADER_LEN, len(pkt) - _HEADER_LEN, self.seq)
        self.transport.write(pkt)
