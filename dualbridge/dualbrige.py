import asyncio
import os
import struct
import sys
import time

import websockets

# Required for .env support (matches the mock dealer approach)
from dotenv import load_dotenv

websocket_clients = set()
tcp_clients = set()

ws_client_ids = {}
ws_next_id = 1


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def log(msg: str) -> None:
    print(f"{_ts()} {msg}", flush=True)


def _decode_hdr(data: bytes):
    """Decode 12-byte header (!III). Returns (cmd,size,seq) or None."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 12:
        return None
    try:
        cmd, size, seq = struct.unpack('!III', data[:12])
        return cmd, size, seq
    except Exception:
        return None


def _load_env() -> None:
    """Load .env next to the script/exe."""
    base_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)


def _get_ports() -> tuple[int, int]:
    """Read ports from env (DUALBRIDGE_TCP_PORT / DUALBRIDGE_WS_PORT) with safe defaults."""
    _load_env()
    tcp_port_s = os.environ.get("DUALBRIDGE_TCP_PORT", "2331")
    ws_port_s = os.environ.get("DUALBRIDGE_WS_PORT", "3331")
    tcp_port = int(tcp_port_s)
    ws_port = int(ws_port_s)
    return tcp_port, ws_port

# 處理 WebSocket 客戶端
# NOTE: API compatibility across websockets versions
# - websockets <=10 calls handler(websocket, path)
# - websockets >=11/12 may call handler(websocket) (path accessible via websocket.path or websocket.request.path)
async def handle_websocket(websocket, path=None):
    if path is None:
        # websockets >= 11/12
        path = getattr(websocket, "path", None)
        if path is None:
            req = getattr(websocket, "request", None)
            if req is not None:
                path = getattr(req, "path", None)

    websocket_clients.add(websocket)
    global ws_next_id
    ws_id = ws_client_ids.get(websocket)
    if ws_id is None:
        ws_id = ws_next_id
        ws_next_id += 1
        ws_client_ids[websocket] = ws_id
    ra = getattr(websocket, "remote_address", None)
    log(f"🌐 WebSocket 連線：id={ws_id} ra={ra} path={path} (clients={len(websocket_clients)})")
    if len(websocket_clients) > 1:
        log(f"⚠️ 注意：目前有 {len(websocket_clients)} 個 WS clients 連線，可能會有另一個 client 送出 STOP/START。")
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                hdr = _decode_hdr(message)
                if hdr:
                    cmd, size, seq = hdr
                    log(f"📨 WS->TCP from id={ws_id} cmd=0x{cmd:08X} size={size} seq={seq} ({len(message)} bytes)")
                else:
                    log(f"📨 WS->TCP from id={ws_id} ({len(message)} bytes, no hdr)")
                for writer in tcp_clients.copy():
                    try:
                        writer.write(message)
                        await writer.drain()
                    except Exception as e:
                        log(f"⚠️ 傳送給 TCP 失敗：{e!r}")
                        tcp_clients.discard(writer)
            else:
                log(f"⚠️ 收到文字訊息但預期 binary：{message}")
    except websockets.exceptions.ConnectionClosed:
        log(f"🔌 WebSocket 離線：{websocket.remote_address}")
    finally:
        websocket_clients.discard(websocket)

# 處理 TCP 客戶端
async def handle_tcp_client(reader, writer):
    addr = writer.get_extra_info('peername')
    log(f"🔌 TCP 連線：{addr}")
    tcp_clients.add(writer)

    # TCP is a stream: we must re-frame packets before forwarding to WebSocket.
    # Packet format: 12-byte header: !III = cmd, size, seq; size includes header.
    buf = bytearray()
    MAX_PACKET = 2 * 1024 * 1024  # 2MB safety guard
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            buf.extend(data)

            # Parse as many complete packets as possible.
            while True:
                if len(buf) < 12:
                    break
                cmd, size, seq = struct.unpack("!III", buf[:12])
                if size < 12 or size > MAX_PACKET:
                    raise ValueError(f"Invalid packet size={size} from TCP {addr}, cmd=0x{cmd:08X} seq={seq}")
                if len(buf) < size:
                    break

                pkt = bytes(buf[:size])
                del buf[:size]
                log(f"📨 TCP->WS cmd=0x{cmd:08X} size={size} seq={seq} (clients={len(websocket_clients)})")

                for websocket in websocket_clients.copy():
                    try:
                        await websocket.send(pkt)
                    except Exception as e:
                        log(f"⚠️ 傳送給 WebSocket 失敗：{e!r}")
                        websocket_clients.discard(websocket)
    except Exception as e:
        log(f"❗ TCP 錯誤：{e!r}")
        raise
    finally:
        tcp_clients.discard(writer)
        writer.close()
        await writer.wait_closed()
        log(f"❌ TCP 離線：{addr}")

# ✅ 這是 Twisted 呼叫的入口點（不直接 await）
def main_dualbrige_websocket_TCPsocket():
    loop = asyncio.get_event_loop()
    loop.create_task(_start_servers())

# ✅ 真正執行 server 的 async coroutine
async def _start_servers():
    tcp_port, websocket_port = _get_ports()

    tcp_server = await asyncio.start_server(handle_tcp_client, "0.0.0.0", tcp_port)
    ws_server = await websockets.serve(handle_websocket, "0.0.0.0", websocket_port)

    log("🚀 雙向橋接中心廣播伺服器啟動")
    log(f"TCP socket 監聽：{tcp_port}")
    log(f"Web socket 監聽：{websocket_port}")

    # Keep running. The WS server stays active as long as the loop is alive.
    await tcp_server.serve_forever()


if __name__ == "__main__":
    # Run as a standalone service.
    asyncio.run(_start_servers())
