import asyncio
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "mock_dealer_games" / "dealer_dragontiger_ws" / "ws_proto.py"
SPEC = importlib.util.spec_from_file_location("ws_proto_fix", TARGET)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
WSDealerProto = mod.WSDealerProto
CMD_LOGIN_R_D2C = mod.CMD_LOGIN_R_D2C


class FakeGUI:
    def __init__(self):
        self.statuses = []
        self.start_enabled = 0

    def set_status(self, text, color=None):
        self.statuses.append((text, color))

    def enable_start_prediction(self):
        self.start_enabled += 1

    def on_first_result(self):
        pass


class FakeApp:
    def __init__(self):
        self.gui = FakeGUI()
        self.proto_ws = None
        self.predicting = False


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


class WSReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FakeApp()

    async def test_connect_sends_login_and_marks_ready(self):
        ws = FakeWS()
        seq = ConnectSequence([ws])
        proto = WSDealerProto(self.app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.2)
            self.assertTrue(proto.logged_in)
            self.assertIs(self.app.proto_ws, proto)
            self.assertEqual(len(ws.sent), 1)
            cmd, size, packet_seq = struct.unpack("!3I", ws.sent[0][:12])
            self.assertEqual(cmd, CMD_LOGIN_R_D2C)
            self.assertEqual(packet_seq, 1)
            self.assertGreaterEqual(self.app.gui.start_enabled, 1)
            await proto.close()

    async def test_initial_connect_failure_recovers_without_process_restart(self):
        ws = FakeWS()
        seq = ConnectSequence([ConnectionError("first failed"), ws])
        proto = WSDealerProto(self.app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.3)
            self.assertTrue(proto.logged_in)
            self.assertGreaterEqual(seq.calls, 2)
            await proto.close()

    async def test_remote_disconnect_reconnects_to_new_session(self):
        first = FakeWS()
        second = FakeWS()
        seq = ConnectSequence([first, second])
        proto = WSDealerProto(self.app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.2)
            self.assertIs(proto.ws, first)
            # Simulate 1011/remote close by terminating the receive iterator.
            first._block.set()
            for _ in range(30):
                if proto.ws is second and proto.logged_in:
                    break
                await asyncio.sleep(0.01)
            self.assertIs(proto.ws, second)
            self.assertTrue(proto.logged_in)
            self.assertGreaterEqual(seq.calls, 2)
            await proto.close()

    async def test_send_failure_marks_session_not_ready_and_supervisor_recovers(self):
        first = FakeWS()
        second = FakeWS()
        seq = ConnectSequence([first, second])
        proto = WSDealerProto(self.app)
        proto._reconnect_min = 0.01
        proto._reconnect_max = 0.02

        with patch.object(mod.websockets, "connect", side_effect=seq):
            await asyncio.wait_for(proto.connect(), timeout=0.2)
            first.fail_send = True
            ok = await proto.send_dispatch_index("DT20261015_1", 1)
            self.assertFalse(ok)
            self.assertFalse(proto.logged_in)
            for _ in range(30):
                if proto.ws is second and proto.logged_in:
                    break
                await asyncio.sleep(0.01)
            self.assertIs(proto.ws, second)
            self.assertTrue(proto.logged_in)
            await proto.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
