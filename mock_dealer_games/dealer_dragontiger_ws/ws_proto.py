"""Compatibility wrapper for the shared detector WebSocket transport.

All reconnect/session lifecycle logic now lives in shared_detector_transport.py
so BAC / DT / Latency can use the same WS implementation.
"""

from pathlib import Path
import sys

_MOCK_GAMES_ROOT = Path(__file__).resolve().parent.parent
if str(_MOCK_GAMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOCK_GAMES_ROOT))

from shared_detector_transport import (  # re-export for existing tests/imports
    CMD_CANCEL_RESULT_D2C,
    CMD_DISPATCH_IDX_D2C,
    CMD_KEEPALIVE,
    CMD_LOGIN,
    CMD_LOGIN_R_D2C,
    CMD_PREDICT_RESULT,
    CMD_SAVE_RESULT_D2C,
    CMD_START_PREDICT_D2C,
    CMD_STOP_PREDICT_D2C,
    SharedWSDealerProtocol,
    resolve_ws_uri,
    websockets,
)


def _resolve_ws_uri() -> str:
    return resolve_ws_uri()


class WSDealerProto(SharedWSDealerProtocol):
    def __init__(self, app):
        super().__init__(app, app_attr="proto_ws")
