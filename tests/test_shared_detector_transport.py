import asyncio
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MOCK_GAMES = ROOT / "mock_dealer_games"
if str(MOCK_GAMES) not in sys.path:
    sys.path.insert(0, str(MOCK_GAMES))

import shared_detector_transport as mod


class FakeGUI:
    def __init__(self):
        self.statuses = []
        self.start_enabled = 0
        self.first_results = 0

    def set_status(self, text, color=None):
        self.statuses.append((text, color))

    def enable_start_prediction(self):
        self.start_enabled += 1

    def disable_start_prediction(self):
        pass

    def disable_stop_prediction(self):
        pass

    def disable_dispatch_buttons(self):
        pass

    def disable_save_result(self):
        pass

    def on_first_result(self):
        self.first_results += 1


class FakeApp:
    def __init__(self, mode="dt"):
        self.ui_mode = mode
        self.gui = FakeGUI()
        self.proto_tcp = None
        self.proto_ws = None
        self.predicting = True
        self.results = []

    def on_predict_result(self, idx, value, score, gmcode_bytes=None):
        self.results.append((idx, value, score, mod.decode_gmcode(gmcode_bytes or b"")))


class FakeTransport:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


class FakeWS:
    def __init__(self, incoming=None, fail_send=False):
        self.incoming = list(incoming or [])
        self.fail_send = fail_send
        self.sent = []
        self.closed = False
        self._block = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.incoming:
            item = self.incoming.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        await self._block.wait()
        raise StopAsyncIteration

    async def send(self, data):
        if self.fail_send:
            raise ConnectionError("simulated send failure")
        self.sent.append(data)

    async def close(self):
        self.closed = True
        self._block.set()


class ConnectSequence:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def __call__(self, uri):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            async def _raise():
                raise item
            return _raise()
        async def _return():
            return item
        return _return()


class IdentityTests(unittest.TestCase):
    def test_known_game_identities(self):
        expected = {
            "dt": (b"DT\x00\x00", b"B021"),
            "latency": (b"DT\x00\x00", b"B021"),
            "bac": (b"BAC\x00", b"B004"),
            "ball3": (b"BALL", b"B003"),
        }
        for mode, pair in expected.items():
            with self.subTest(mode=mode):
                ident = mod.resolve_detector_identity(FakeApp(mode))
                self.assertEqual((ident.gmtype, ident.vid), pair)

    def test_tcp_fragmented_login_and_prediction(self):
        app = FakeApp("bac")
        proto = mod.SharedTCPDealerProtocol(app)
        tx = FakeTransport()
        proto.connection_made(tx)

        login = struct.pack("!3I", mod.CMD_LOGIN, 12, 1)
        proto.data_received(login[:5])
        self.assertEqual(tx.writes, [])
        proto.data_received(login[5:])
        self.assertTrue(proto.logged_in)
        cmd, size, seq = struct.unpack("!3I", tx.writes[0][:12])
        self.assertEqual(cmd, mod.CMD_LOGIN_R_D2C)
        code, gmtype, vid = struct.unpack("!I4s4s", tx.writes[0][12:])
        self.assertEqual(gmtype, b"BAC\x00")
        self.assertEqual(vid, b"B004")

        body = struct.pack("!14sh2hd", b"BAC261015_1".ljust(14, b"\x00"), 1, 2, 47, 0.88)
        pkt = struct.pack("!3I", mod.CMD_PREDICT_RESULT, 12 + len(body), 2) + body
        proto.data_received(pkt[:17])
        proto.data_received(pkt[17:])
        self.assertEqual(len(app.results), 1)
        self.assertEqual(app.results[0][0:2], (2, 47))


class WSReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_failure_and_remote_disconnect_recover(self):
        app = FakeApp("dt")
        first = FakeWS()
        second = FakeWS()
        seq = ConnectSequence([ConnectionError("first failed"), first, second])
        proto = mod.SharedWSDealerProtocol(app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.3)
            self.assertIs(proto.ws, first)
            self.assertTrue(proto.logged_in)
            first._block.set()
            for _ in range(40):
                if proto.ws is second and proto.logged_in:
                    break
                await asyncio.sleep(0.01)
            self.assertIs(proto.ws, second)
            self.assertTrue(proto.logged_in)
            self.assertGreaterEqual(seq.calls, 3)
            await proto.close()

    async def test_send_failure_recovers(self):
        app = FakeApp("bac")
        first = FakeWS()
        second = FakeWS()
        seq = ConnectSequence([first, second])
        proto = mod.SharedWSDealerProtocol(app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.2)
            first.fail_send = True
            ok = await proto.send_dispatch_index("BAC261015_1", 1)
            self.assertFalse(ok)
            for _ in range(40):
                if proto.ws is second and proto.logged_in:
                    break
                await asyncio.sleep(0.01)
            self.assertIs(proto.ws, second)
            self.assertTrue(proto.logged_in)
            await proto.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
