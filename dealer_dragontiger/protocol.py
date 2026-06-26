# dealer_dragontiger/protocol.py
import asyncio, struct, logging

log = logging.getLogger("DTProto")

# Detector-side command constants (dealer → detector = BA ****)
CMD_LOGIN_R_D2C       = 0xBA0002
CMD_START_PREDICT_D2C = 0xBA0003
CMD_STOP_PREDICT_D2C  = 0xBA0004
CMD_DISPATCH_IDX_D2C  = 0xBA0006

# Detector-side reply (AB 0004)
CMD_KEEPALIVE = 0xAB0001
CMD_LOGIN = 0xAB0002
CMD_PREDICT_RESULT    = 0xAB0004

_HEADER_FMT = "!3I"          # cmd, size, seq  (network byte-order)
_HEADER_LEN = struct.calcsize(_HEADER_FMT)

class MockDealerAppProtocol(asyncio.Protocol):
    """
    One instance per detector TCP connection.  Needs a reference to the
    DragonTigerApp (`self.app`) so it can update cards & status.
    """
    def __init__(self, app):
        self.app          = app
        self.transport    = None
        self.seq          = 0
        self.logged_in    = False
        self.login_sent   = False
        self.svrid        = b"1001"             # 4-byte ASCII, padded

    # ------------------------------------------------ asyncio callbacks --
    def connection_made(self, transport):
        self.transport      = transport
        self.app.proto      = self
        self._send_login_reply()
        self.app.gui.set_status("Login OK – ready.", color="green")
        self.app.gui.enable_start_prediction()

    def connection_lost(self, exc):
        self.transport    = None
        self.logged_in    = False
        self.app.proto    = None
        self.app.gui.set_status("Detector disconnected.", color="red")
        self.app.gui.disable_start_prediction()
        self.app.gui.disable_stop_prediction()
        self.app.gui.disable_dispatch_buttons()

    def data_received(self, data: bytes):
        offset = 0
        while offset + _HEADER_LEN <= len(data):
            # --- unpack header ---
            cmd, size, seq = struct.unpack_from("!3i", data, offset)
            log.info(f"[TCP] Header: cmd=0x{cmd:06X}, size={size}, seq={seq}")
            packet_len = size

            # --- skip incomplete check for body-less cmds ---
            if cmd not in (CMD_KEEPALIVE, CMD_LOGIN):
                if len(data) - offset < packet_len:
                    log.warning("[RX] Incomplete packet, waiting for more data")
                    return  # wait for next recv

            # --- process ---
            if cmd == CMD_KEEPALIVE:
                log.info("[TCP] Keepalive packet received.")
            elif cmd == CMD_LOGIN:
                log.info("[TCP] CMD_LOGIN packet received.")
            elif cmd == CMD_PREDICT_RESULT:
                body = data[offset + _HEADER_LEN : offset + packet_len]
                log.info("[TCP] PREDICT_RESULT bytes: %s", body.hex())
                self._handle_prediction(body)
                offset += packet_len
                continue        # ← make sure this is still here!
            else:
                log.warning(f"[TCP] Unknown or unhandled cmd=0x{cmd:06X}, skipping.")

            # --- move to next packet ---
            offset += packet_len

    # ------------------------------------------------ public helpers -----
    def send_start_predict(self, gmcode: str):
        if not self.logged_in: return
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14, b'\x00'), 2)
        self._send(CMD_START_PREDICT_D2C, body)

    def send_stop_predict(self, gmcode: str):
        if not self.logged_in: return
        body = struct.pack("!14sh", gmcode.encode("ascii")[:14].ljust(14, b'\x00'), 0)
        self._send(CMD_STOP_PREDICT_D2C, body)

    def send_dispatch_index(self, gmcode: str, idx: int):
        """
        BA 0006  – Dispatch Index
        Body = 4-byte gmstate (we send 0)
            14-byte gmcode  (ASCII, NUL-padded)
                2-byte index   (unsigned short, 0-5)

        Total body length = 20 bytes  → size field in header = 12 + 20 = 32
        """
        if not self.logged_in:
            return

        gmstate = 0
        gm14    = gmcode.encode('ascii')[:14].ljust(14, b'\x00')
        body    = struct.pack('!14sh', gm14, idx)

        self._send(CMD_DISPATCH_IDX_D2C, body)   # BA 0006 constant

    # ---------------------------------------------------------------- internal ----
    def _send_login_reply(self):
        """
        BA-0002  (login reply) – format exactly as your legacy code:
            uint32 code       -> 0
            char[4] gmtype    -> b'DT  '
            char[4] svrid     -> echoed from detector
        Total body length = 12 bytes
        """
        if self.login_sent:          # already sent once
            return

        self.login_sent = True
        self.logged_in  = True       # detector treats this as ACK

        gmtype = b'DT'             # Dragon-Tiger game id (4 bytes)

        # build 12-byte body: code(0) + gmtype + svrid
        body = struct.pack("!i4s4s", 0, gmtype, self.svrid)   # 4+4+4 = 12
        assert len(body) == 12        # safety check

        self._send(CMD_LOGIN_R_D2C, body)  # BA 0002
        log.info("LOGIN_R sent (12-byte body)")

    def _handle_prediction(self, body: bytes):
        if len(body) < struct.calcsize("!14sh"):
            log.warning("[Prediction] body too short")
            return

        gamecode, count = struct.unpack_from("!14sh", body, 0)
        offset = struct.calcsize("!14sh")

        for n in range(count):
            if len(body) < offset + struct.calcsize("!2hd"):
                log.warning("[Prediction] truncated entry n=%d", n)
                return                     # or break, your choice
            idx, dealer_classid, score = struct.unpack_from("!2hd", body, offset)
            offset += struct.calcsize("!2hd")

            log.info("[Prediction] idx=%d card=%d score=%.3f", idx, dealer_classid, score)
            self.app.gui.update_card(idx, dealer_classid)

    # ------------------------------------------------ low-level send -----
    def _send(self, cmd: int, body: bytes = b""):
        """
        Low-level sender – packs `cmd`, `size`, `seq` with !3i.
        """
        if not self.transport:
            raise RuntimeError("Detector socket is not connected")

        self.seq = (self.seq + 1) & 0xFFFFFFFF          # roll-over ok
        pkt  = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq)
        pkt += body
        self.transport.write(pkt)
