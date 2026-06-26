import asyncio, struct, logging
log = logging.getLogger("DTProto")

CMD_LOGIN_R_D2C       = 0xBA0002
CMD_START_PREDICT_D2C = 0xBA0003
CMD_STOP_PREDICT_D2C  = 0xBA0004
CMD_DISPATCH_IDX_D2C  = 0xBA0006
CMD_SAVE_RESULT_D2C   = 0xBA0007
CMD_CANCEL_RESULT_D2C = 0xBA0008

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
        self.app.gui.set_status("Detector disconnected.", color="red")
        self.app.gui.disable_start_prediction()
        self.app.gui.disable_stop_prediction()
        self.app.gui.disable_dispatch_buttons()
        self.app.gui.disable_save_result()

    def data_received(self, data: bytes):
        off = 0
        while off + _HEADER_LEN <= len(data):
            cmd, size, seq = struct.unpack_from(_HEADER_FMT, data, off)
            pkt_len = size

            if cmd == CMD_LOGIN:
                self._send_login_reply()
            elif cmd == CMD_PREDICT_RESULT:
                body = data[off + _HEADER_LEN : off + pkt_len]
                self._handle_prediction(body)
                off += pkt_len
                continue
            off += pkt_len

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

    def send_cancel_result(self, gmcode: str):
        if not self.logged_in: return
        gm_bytes = gmcode.encode("ascii","ignore")[:14].ljust(14,b"\x00")
        body = struct.pack("!14s", gm_bytes)
        self._send(CMD_CANCEL_RESULT_D2C, body)

    # internals
    def _send_login_reply(self):
        if self.login_sent: return
        self.login_sent = True
        self.logged_in  = True
        body = struct.pack("!I4s4s", 0, self.app.game_code_4(), self.app.login_vid.encode("ascii","ignore")[:4].ljust(4,b"\x00"))
        self._send(CMD_LOGIN_R_D2C, body)
        self.app.gui.set_status("Detector ready (TCP).", color="green")
        self.app.gui.enable_start_prediction()

    def _handle_prediction(self, body: bytes):
        if not getattr(self.app, "_ready_to_dispatch", False):
            self.app._ready_to_dispatch = True
            self.app.gui.on_prediction_started()
        self.app.gui.on_first_result()

        if len(body) < struct.calcsize("!14sh"):
            return
        gmcode_raw, count = struct.unpack_from("!14sh", body, 0)
        gmcode = bytes(gmcode_raw).decode("utf-8", errors="ignore").rstrip("\x00")
        off = struct.calcsize("!14sh")
        results = []
        for _ in range(count):
            if len(body) < off + struct.calcsize("!2hd"):
                return
            idx, dealer_classid, score = struct.unpack_from("!2hd", body, off)
            off += struct.calcsize("!2hd")
            results.append((int(idx), int(dealer_classid), float(score)))
        self.app.update_slots(gmcode, results)

    def _send(self, cmd: int, body: bytes = b""):
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
        # 📏 log packet length when sending
        log.info("[TCP->Detector] cmd=0x%06X size=%d (hdr=%d body=%d) seq=%d",
                 cmd, len(pkt), _HEADER_LEN, len(pkt) - _HEADER_LEN, self.seq)
        self.transport.write(pkt)
