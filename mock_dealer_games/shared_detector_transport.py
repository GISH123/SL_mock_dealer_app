from __future__ import annotations

import asyncio
import logging
import os
import struct
from dataclasses import dataclass
from typing import Iterable

import websockets

CMD_LOGIN_R_D2C = 0xBA0002
CMD_START_PREDICT_D2C = 0xBA0003
CMD_STOP_PREDICT_D2C = 0xBA0004
CMD_DISPATCH_IDX_D2C = 0xBA0006
CMD_SAVE_RESULT_D2C = 0xBA0007
CMD_CANCEL_RESULT_D2C = 0xBA0008

CMD_KEEPALIVE = 0xAB0001
CMD_LOGIN = 0xAB0002
CMD_PREDICT_RESULT = 0xAB0004

_HEADER_FMT = "!3I"
_HEADER_LEN = struct.calcsize(_HEADER_FMT)
_RESULT_HEAD_FMT = "!14sh"
_RESULT_HEAD_LEN = struct.calcsize(_RESULT_HEAD_FMT)
_RESULT_ITEM_FMT = "!2hd"
_RESULT_ITEM_LEN = struct.calcsize(_RESULT_ITEM_FMT)

log_tcp = logging.getLogger("DetectorTCP")
log_ws = logging.getLogger("DetectorWS")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _clean_env(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().strip('"').strip("'")
    return value or None


def resolve_ws_uri() -> str:
    uri = _clean_env(os.getenv("WS_URI"))
    if uri:
        return uri
    host = _clean_env(os.getenv("WS_HOST"))
    port = _clean_env(os.getenv("WS_PORT"))
    if host and port:
        return f"ws://{host}:{port}"
    return "ws://127.0.0.1:3331"


@dataclass(frozen=True)
class DetectorIdentity:
    gmtype: bytes
    vid: bytes

    def __post_init__(self):
        object.__setattr__(self, "gmtype", bytes(self.gmtype[:4]).ljust(4, b"\x00"))
        object.__setattr__(self, "vid", bytes(self.vid[:4]).ljust(4, b"\x00"))


def _to_wire4(value, default: bytes) -> bytes:
    if value is None:
        return default[:4].ljust(4, b"\x00")
    if isinstance(value, bytes):
        raw = value
    else:
        raw = str(value).encode("ascii", "ignore")
    return raw[:4].ljust(4, b"\x00")


def resolve_detector_identity(app) -> DetectorIdentity:
    """Resolve protocol login identity without tying transport to one game.

    Priority:
      1. LOGIN_GMTYPE / LOGIN_VID environment overrides.
      2. app.game_code_4() / app.login_vid when supplied by a game app.
      3. Known ui_mode/game_mode mappings.

    The mappings preserve the identities already present in this repository:
      DT/Latency -> DT / B021
      BAC        -> BAC / B004
      BALL3      -> BALL / B003
    """
    env_gmtype = _clean_env(os.getenv("LOGIN_GMTYPE"))
    env_vid = _clean_env(os.getenv("LOGIN_VID"))

    app_gmtype = None
    game_code = getattr(app, "game_code_4", None)
    if callable(game_code):
        try:
            app_gmtype = game_code()
        except Exception:
            app_gmtype = None

    app_vid = getattr(app, "login_vid", None)

    mode = str(
        getattr(app, "ui_mode", "")
        or getattr(app, "game_mode", "")
        or getattr(app, "game_name", "")
        or ""
    ).strip().lower()

    if mode in {"bac", "bac6", "baccarat"}:
        default_gmtype, default_vid = b"BAC", b"B004"
    elif mode in {"ball3", "ball", "ball_3"}:
        default_gmtype, default_vid = b"BALL", b"B003"
    else:
        # Preserve historical DragonTiger/latency behavior.
        default_gmtype, default_vid = b"DT", b"B021"

    gmtype = _to_wire4(env_gmtype or app_gmtype, default_gmtype)
    vid = _to_wire4(env_vid or app_vid, default_vid)
    return DetectorIdentity(gmtype=gmtype, vid=vid)


def wire_gmcode(gmcode: str | None) -> bytes:
    return (gmcode or "").encode("ascii", "ignore")[:14].ljust(14, b"\x00")


def decode_gmcode(gmcode_bytes: bytes) -> str:
    return bytes(gmcode_bytes).split(b"\x00", 1)[0].decode("ascii", "ignore")


def parse_prediction_body(body: bytes):
    if len(body) < _RESULT_HEAD_LEN:
        return None
    gmcode_bytes, count = struct.unpack_from(_RESULT_HEAD_FMT, body, 0)
    if count < 0:
        return None
    off = _RESULT_HEAD_LEN
    items = []
    for _ in range(count):
        if off + _RESULT_ITEM_LEN > len(body):
            return None
        idx, value, score = struct.unpack_from(_RESULT_ITEM_FMT, body, off)
        off += _RESULT_ITEM_LEN
        items.append((int(idx), int(value), float(score)))
    return gmcode_bytes, items


def _gui_call(app, name: str, *args, **kwargs):
    gui = getattr(app, "gui", None)
    fn = getattr(gui, name, None) if gui is not None else None
    if callable(fn):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None
    return None


def _set_status(app, text: str, color: str | None = None):
    if getattr(app, "gui", None) is not None:
        _gui_call(app, "set_status", text, color=color)
        return
    fn = getattr(app, "log", None)
    if callable(fn):
        try:
            fn(text)
        except Exception:
            pass


def _round_accepts_results(app) -> bool:
    # Apps that explicitly expose `predicting` use it as the source of truth.
    if hasattr(app, "predicting"):
        return bool(getattr(app, "predicting", False))
    return True


def deliver_prediction(app, gmcode_bytes: bytes, items: Iterable[tuple[int, int, float]]):
    if not _round_accepts_results(app):
        return

    items = list(items)
    _gui_call(app, "on_first_result")

    on_predict_result = getattr(app, "on_predict_result", None)
    if callable(on_predict_result):
        for idx, value, score in items:
            on_predict_result(idx, value, score, gmcode_bytes=gmcode_bytes)
        return

    gmcode = decode_gmcode(gmcode_bytes)

    update_slots = getattr(app, "update_slots", None)
    if callable(update_slots):
        update_slots(gmcode, items)
        return

    update_groups = getattr(app, "update_groups", None)
    if callable(update_groups):
        groups = {}
        for idx, value, score in items:
            groups.setdefault(idx, []).append((value, score))
        update_groups(gmcode, groups)
        return

    for idx, value, _score in items:
        _gui_call(app, "update_card", idx, value)


class SharedTCPDealerProtocol(asyncio.Protocol):
    """Shared detector TCP protocol for DT/BAC/Latency/BALL3 style games."""

    def __init__(self, app, *, app_attr: str = "proto_tcp"):
        self.app = app
        self.app_attr = app_attr
        self.transport = None
        self.seq = 0
        self.logged_in = False
        self.login_sent = False
        self._buf = bytearray()

    def connection_made(self, transport):
        self.transport = transport
        setattr(self.app, self.app_attr, self)
        self.logged_in = False
        self.login_sent = False
        self._buf.clear()
        _set_status(self.app, "TCP connected, waiting for LOGIN…", color="orange")
        _gui_call(self.app, "disable_save_result")

    def connection_lost(self, exc):
        self.transport = None
        if getattr(self.app, self.app_attr, None) is self:
            setattr(self.app, self.app_attr, None)
        self.logged_in = False
        self.login_sent = False
        self._buf.clear()
        _set_status(self.app, "Detector disconnected (TCP).", color="red")
        _gui_call(self.app, "disable_start_prediction")
        _gui_call(self.app, "disable_stop_prediction")
        _gui_call(self.app, "disable_dispatch_buttons")
        _gui_call(self.app, "disable_save_result")

    def data_received(self, data: bytes):
        self._buf += data
        while True:
            if len(self._buf) < _HEADER_LEN:
                return
            cmd, size, _seq = struct.unpack_from(_HEADER_FMT, self._buf, 0)
            if size < _HEADER_LEN:
                del self._buf[0]
                continue
            if len(self._buf) < size:
                return
            pkt = bytes(self._buf[:size])
            del self._buf[:size]
            body = pkt[_HEADER_LEN:]

            if cmd == CMD_LOGIN:
                self._send_login_reply()
            elif cmd == CMD_PREDICT_RESULT:
                parsed = parse_prediction_body(body)
                if parsed is not None:
                    gmcode_bytes, items = parsed
                    deliver_prediction(self.app, gmcode_bytes, items)

    def send_start_predict(self, gmcode: str):
        if not self.logged_in:
            return False
        return self._send(CMD_START_PREDICT_D2C, struct.pack("!14sh", wire_gmcode(gmcode), 2))

    def send_stop_predict(self, gmcode: str):
        if not self.logged_in:
            return False
        return self._send(CMD_STOP_PREDICT_D2C, struct.pack("!14sh", wire_gmcode(gmcode), 0))

    def send_dispatch_index(self, gmcode: str, idx: int):
        if not self.logged_in:
            return False
        return self._send(CMD_DISPATCH_IDX_D2C, struct.pack("!14sh", wire_gmcode(gmcode), int(idx)))

    def send_save_result(self, gmcode: str):
        if not self.logged_in:
            return False
        return self._send(CMD_SAVE_RESULT_D2C, struct.pack("!14s", wire_gmcode(gmcode)))

    def send_cancel_result(self, gmcode: str):
        if not self.logged_in:
            return False
        return self._send(CMD_CANCEL_RESULT_D2C, struct.pack("!14s", wire_gmcode(gmcode)))

    def _send_login_reply(self):
        if self.login_sent or self.transport is None:
            return False
        identity = resolve_detector_identity(self.app)
        self.login_sent = True
        self.logged_in = True
        body = struct.pack("!I4s4s", 0, identity.gmtype, identity.vid)
        ok = self._send(CMD_LOGIN_R_D2C, body)
        if ok:
            _set_status(self.app, "Detector ready (TCP).", color="green")
            _gui_call(self.app, "enable_start_prediction")
        return ok

    def _send(self, cmd: int, body: bytes = b""):
        if self.transport is None:
            return False
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
        log_tcp.info(
            "[TCP->Detector] cmd=0x%06X size=%d (hdr=%d body=%d) seq=%d",
            cmd, len(pkt), _HEADER_LEN, len(body), self.seq,
        )
        self.transport.write(pkt)
        return True


class SharedWSDealerProtocol:
    """Shared self-healing detector WebSocket protocol.

    One supervisor owns the session. Any initial-connect failure, graceful close,
    keepalive timeout/1011, or send failure tears down the old socket and retries
    with bounded exponential backoff.
    """

    def __init__(self, app, *, app_attr: str = "proto_ws", uri: str | None = None):
        self.app = app
        self.app_attr = app_attr
        self.ws = None
        self.seq = 0
        self.logged_in = False
        self.uri = uri

        self._supervisor_task = None
        self._connected_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._reconnect_min = max(0.1, _env_float("WS_RECONNECT_MIN_SEC", 1.0))
        self._reconnect_max = max(self._reconnect_min, _env_float("WS_RECONNECT_MAX_SEC", 5.0))
        self._close_timeout = max(0.1, _env_float("WS_CLOSE_TIMEOUT_SEC", 2.0))

    async def connect(self):
        if not self.uri:
            self.uri = resolve_ws_uri()
        if self._supervisor_task is None or self._supervisor_task.done():
            self._stop_event.clear()
            self._supervisor_task = asyncio.create_task(
                self._connection_supervisor(),
                name="mock-dealer-ws-supervisor",
            )
        await self._connected_event.wait()

    async def close(self):
        self._stop_event.set()
        self.logged_in = False
        self._connected_event.clear()
        task = self._supervisor_task
        self._supervisor_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                log_ws.exception("WS supervisor failed while closing")
        await self._close_socket(self.ws)
        self.ws = None

    async def wait_until_ready(self, timeout: float | None = None) -> bool:
        if self.logged_in:
            return True
        try:
            if timeout is None:
                await self._connected_event.wait()
            else:
                await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            return self.logged_in
        except asyncio.TimeoutError:
            return False

    async def _connection_supervisor(self):
        delay = self._reconnect_min
        while not self._stop_event.is_set():
            ws = None
            try:
                _set_status(self.app, f"Connecting WS : {self.uri}", color="orange")
                log_ws.info("WS connecting to %s", self.uri)
                ws = await websockets.connect(self.uri)
                self.ws = ws
                self.seq = 0
                self.logged_in = False
                setattr(self.app, self.app_attr, self)

                await self._send_login_reply(raise_on_error=True)
                self.logged_in = True
                self._connected_event.set()
                delay = self._reconnect_min

                _set_status(self.app, f"Detector ready (WS) : {self.uri}", color="green")
                if not getattr(self.app, "predicting", False):
                    _gui_call(self.app, "enable_start_prediction")
                log_ws.info("WS connected and ready: %s", self.uri)

                await self._recv_loop(ws)
                if not self._stop_event.is_set():
                    log_ws.warning("WS receive loop ended; reconnecting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._stop_event.is_set():
                    log_ws.warning("WS connection/session lost: %s", exc, exc_info=True)
            finally:
                if self.ws is ws:
                    self.logged_in = False
                    self._connected_event.clear()
                    self.ws = None
                await self._close_socket(ws)

            if self._stop_event.is_set():
                break
            _set_status(self.app, f"WS disconnected; reconnecting in {delay:.1f}s …", color="orange")
            log_ws.info("WS reconnect scheduled in %.1fs", delay)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            delay = min(self._reconnect_max, delay * 2.0)

    async def _recv_loop(self, ws):
        async for raw in ws:
            self._handle_raw(raw)

    async def _close_socket(self, ws):
        if ws is None:
            return
        try:
            await asyncio.wait_for(ws.close(), timeout=self._close_timeout)
        except asyncio.TimeoutError:
            log_ws.warning("WS close timed out; abandoning old session")
        except Exception:
            pass

    def _handle_raw(self, data: bytes):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            return
        off = 0
        while off + _HEADER_LEN <= len(data):
            cmd, size, _seq = struct.unpack_from(_HEADER_FMT, data, off)
            if size < _HEADER_LEN:
                return
            if off + size > len(data):
                return
            body = bytes(data[off + _HEADER_LEN: off + size])
            off += size
            if cmd == CMD_PREDICT_RESULT:
                parsed = parse_prediction_body(body)
                if parsed is not None:
                    gmcode_bytes, items = parsed
                    deliver_prediction(self.app, gmcode_bytes, items)

    async def _send_login_reply(self, *, raise_on_error: bool = False):
        identity = resolve_detector_identity(self.app)
        body = struct.pack("!I4s4s", 0, identity.gmtype, identity.vid)
        return await self._send(CMD_LOGIN_R_D2C, body, raise_on_error=raise_on_error)

    async def send_start_predict(self, gmcode: str):
        return await self._send(CMD_START_PREDICT_D2C, struct.pack("!14sh", wire_gmcode(gmcode), 2))

    async def send_stop_predict(self, gmcode: str):
        return await self._send(CMD_STOP_PREDICT_D2C, struct.pack("!14sh", wire_gmcode(gmcode), 0))

    async def send_dispatch_index(self, gmcode: str, idx: int):
        return await self._send(CMD_DISPATCH_IDX_D2C, struct.pack("!14sh", wire_gmcode(gmcode), int(idx)))

    async def send_save_result(self, gmcode: str):
        return await self._send(CMD_SAVE_RESULT_D2C, struct.pack("!14s", wire_gmcode(gmcode)))

    async def send_cancel_result(self, gmcode: str):
        return await self._send(CMD_CANCEL_RESULT_D2C, struct.pack("!14s", wire_gmcode(gmcode)))

    async def _send(self, cmd: int, body: bytes = b"", *, raise_on_error: bool = False):
        ws = self.ws
        if ws is None:
            exc = ConnectionError("WebSocket is not connected")
            if raise_on_error:
                raise exc
            log_ws.warning("[WS->Detector] skip cmd=0x%06X: %s", cmd, exc)
            return False

        self.seq = (self.seq + 1) & 0xFFFFFFFF
        pkt = struct.pack(_HEADER_FMT, cmd, _HEADER_LEN + len(body), self.seq) + body
        log_ws.info(
            "[WS->Detector] cmd=0x%06X size=%d (hdr=%d body=%d) seq=%d",
            cmd, len(pkt), _HEADER_LEN, len(body), self.seq,
        )
        try:
            async with self._send_lock:
                if self.ws is not ws:
                    raise ConnectionError("WebSocket session changed before send")
                await ws.send(pkt)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.ws is ws:
                self.logged_in = False
                self._connected_event.clear()
            log_ws.warning("[WS->Detector] send failed cmd=0x%06X: %s", cmd, exc)
            await self._close_socket(ws)
            if raise_on_error:
                raise
            return False
