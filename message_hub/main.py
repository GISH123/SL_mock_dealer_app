import os
import sys
import asyncio
import struct
import httpx
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ─── Bootstrap and logging ─────────────────────────────
# --- PyInstaller bootstrap ------------------------------------
import os, sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys, "_MEIPASS"):
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)

from common.scramble_utils import encode_payload
TOKEN = os.environ["AUTH_TOKEN"]
# --------------------------------------------------------------


from utils.logging_utils import init_logger

log = init_logger("message_hub").info

# ─── Constants ─────────────────────────────────────────
CMD_START_RECORD = 0x20001
CMD_STOP_RECORD  = 0x20002
CMD_START_PLACE  = 0x20003
CMD_STOP_PLACE   = 0x20004
CMD_KEEPALIVE    = 0x2000F
CMD_INPUTJSON    = 0x32001
CMD_SCENE_SWITCH = 0x31001

PACKET_HEADER_LEN = 12  # cmd (4) + size (4) + seq (4)

MSG_HUB_IP   = os.environ["MSG_HUB_BIND_IP"]
MSG_HUB_PORT = int(os.environ["MSG_HUB_BIND_PORT"])

FM_GATEWAY_URL  = f"http://{os.environ['FM_GATEWAY_SERVICE_IP']}:{os.environ['FM_GATEWAY_SERVICE_PORT']}"
DVR_GATEWAY_URL = f"http://{os.environ['DVR_GATEWAY_SERVICE_IP']}:{os.environ['DVR_GATEWAY_SERVICE_PORT']}"
DVR_TARGET_IP   = os.environ["DVR_TARGET_IP"]
DVR_TARGET_PORT   = os.environ["DVR_TARGET_PORT"]

# ─── MessageHub Protocol ───────────────────────────────
class MessageHubProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.buffer = bytearray()

    def connection_made(self, transport):
        self.transport = transport
        peer = transport.get_extra_info("peername")
        log(f"[Hub] Connection from {peer}")

    def data_received(self, data):
        self.buffer.extend(data)
        while len(self.buffer) >= PACKET_HEADER_LEN:
            cmd, size, seq = struct.unpack("!I I I", self.buffer[:PACKET_HEADER_LEN])
            if len(self.buffer) < size:
                return
            packet = self.buffer[:size]
            del self.buffer[:size]
            asyncio.create_task(self.handle_packet(cmd, packet))

    async def handle_packet(self, cmd, body):
        if cmd in (CMD_INPUTJSON, CMD_SCENE_SWITCH):
            await self._send_to_fm(cmd, body)
        elif cmd in (CMD_START_RECORD, CMD_STOP_RECORD, CMD_START_PLACE, CMD_STOP_PLACE, CMD_KEEPALIVE):
            await self._send_to_dvr(cmd, body)
        else:
            log(f"[Hub] Unknown command: 0x{cmd:X}")

    async def _send_to_fm(self, cmd, body):
        try:
            cmd, size, seq = struct.unpack("!I I I", body[:12])
            table, devid, streamid, payload_len = struct.unpack("!4s 4s 12s H", body[12:34])
            method_flag = body[34:35]
            payload_data = body[35:35 + payload_len].decode(errors="ignore").strip("\0")

            table = table.decode(errors="ignore").strip("\0")
            devid = devid.decode(errors="ignore").strip("\0")
            streamid = streamid.decode(errors="ignore").strip("\0")
            use_post = method_flag == b"\x01"

            plain = {
                "route": "inputjson" if cmd == CMD_INPUTJSON else "scene",
                "devId": devid,
                "streamId": streamid,
                "tableId": table,
                "inputName": payload_data if cmd == CMD_INPUTJSON else None,
                "sceneName": payload_data if cmd == CMD_SCENE_SWITCH else None,
            }
            cipher = encode_payload(plain)
            url = f"{FM_GATEWAY_URL.rstrip('/')}/v"
            params = {"p": cipher, "t": TOKEN}

            # # Determine FM Gateway route based on cmd
            # if cmd == CMD_INPUTJSON:
            #     route = "/api/forward_inputjson"       # ✅ fixed
            # elif cmd == CMD_SCENE_SWITCH:
            #     route = "/api/forward_scene_switch"    # ✅ fixed
            # else:
            #     log(f"[Hub→FM] ❌ Unknown FM command: 0x{cmd:X}")
            #     return

            # url = f"{FM_GATEWAY_URL.rstrip('/')}{route}"
            url = f"{FM_GATEWAY_URL.rstrip('/')}/v"     # ← single obfuscated entry
            log(f"[Hub→FM] Connecting to FM Gateway: {url}")

            async with httpx.AsyncClient() as client:
            #     if use_post:
            #         log(f"[Hub→FM] Preparing to POST → {url} with body: {payload}")
            #         resp = await client.post(url, json=payload)
            #     else:
            #         log(f"[Hub→FM] Preparing to GET → {url} with params: {payload}")
            #         resp = await client.get(url, params=payload)
            #     log(f"[Hub→FM] ← Status {resp.status_code} Response: {resp.text}")
                if use_post:
                    log(f"[Hub→FM] POST {url} (body hidden)")
                    resp = await client.post(url, json={"p": cipher, "t": TOKEN})
                else:
                    log(f"[Hub→FM] GET  {url}?p=<hidden>&t=<token>")
                    resp = await client.get(url, params={"p": cipher, "t": TOKEN})
                log(f"[Hub→FM] ← Status {resp.status_code} Response: {resp.text}")
        except Exception as e:
            log(f"[Hub→FM] ❌ Exception: {e}")

    async def _send_to_dvr(self, cmd, body):
        try:
            if len(body) != 30:
                log(f"[Hub→DVR] ❌ Invalid DVR packet size: {len(body)} bytes")
                return

            cmd, size, ver, table, gmcode = struct.unpack("!I I H 4s 16s", body)
            table = table.decode(errors="ignore").strip("\0")
            gmcode = gmcode.decode(errors="ignore").strip("\0")

            # endpoint = {
            #     CMD_START_RECORD: "/record/start",
            #     CMD_STOP_RECORD:  "/record/stop",
            #     CMD_START_PLACE:  "/place/start",
            #     CMD_STOP_PLACE:   "/place/stop",
            #     CMD_KEEPALIVE:    "/keepalive"
            # }[cmd]

            # body_data = {
            #     "gmcode": gmcode,
            #     "table": table,
            #     "dvr_ip": DVR_TARGET_IP,
            #     "dvr_port": DVR_TARGET_PORT
            # }
            # url = f"{DVR_GATEWAY_URL}{endpoint}"

            plain = {
                "route": "record" if cmd in (CMD_START_RECORD, CMD_STOP_RECORD) else "place",
                "action": "start" if cmd in (CMD_START_RECORD, CMD_START_PLACE) else "stop",
                "gmcode": gmcode,
                "table": table,
                "dvr_ip": DVR_TARGET_IP,
                "dvr_port": DVR_TARGET_PORT,
            }
            cipher = encode_payload(plain)
            url = f"{DVR_GATEWAY_URL.rstrip('/')}/d"
            params = {"p": cipher, "t": TOKEN}

            log(f"[Hub→DVR] Posting to DVR Gateway: {url} , (body hidden)")
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={"p": cipher, "t": TOKEN})
                log(f"[Hub→DVR] {url} Status {resp.status_code} Response: {resp.text}")
        except Exception as e:
            log(f"[Hub→DVR] ❌ Error: {e}")

# ─── Entry point ───────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Message Hub TCP Server")
    parser.add_argument("--port", type=int, default=MSG_HUB_PORT, help="Hub listen port")
    args = parser.parse_args()

    async def run_server():
        log(f"[message_hub] 🟢 Binding to {MSG_HUB_IP}:{args.port}")
        loop = asyncio.get_running_loop()
        server = await loop.create_server(
            lambda: MessageHubProtocol(),
            host=MSG_HUB_IP,
            port=args.port
        )
        log(f"[message_hub] 🟢 Server bound and listening on {MSG_HUB_IP}:{args.port}")
        async with server:
            await server.serve_forever()

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        log("[message_hub] 🛑 Server stopped by user")

if __name__ == "__main__":
    main()
