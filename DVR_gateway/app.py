"""
DVR_gateway/app.py
──────────────────
FastAPI bridge that converts HTTP ↔️ binary DVR protocol.
"""

import asyncio, struct, os
from pathlib import Path
from dotenv import load_dotenv
from enum import IntEnum
from typing import Literal, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

# ── environment ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "config.env", override=True)

DVR_TARGET_IP   = os.environ["DVR_TARGET_IP"]
DVR_TARGET_PORT = int(os.environ["DVR_TARGET_PORT"])

# ── logging setup ────────────────────────────────────────────────────────────
import logging
from dotenv import load_dotenv
import os, asyncio, struct, enum
# … (keep your other imports) …

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "config.env", override=True)

MODE        = os.environ.get("DVR_GATEWAY_MODE", "http").lower()  # "http" or "https"
LOGGER_NAME = f"dvr_gateway_{MODE}"

logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    from utils.logging_utils import init_logger
    logger = init_logger(LOGGER_NAME)

logger.info(f"[{LOGGER_NAME}] app 🎯 Target is {DVR_TARGET_IP}:{DVR_TARGET_PORT}")

# ── constants ────────────────────────────────────────────────────────────────
class Cmd(IntEnum):
    START_RECORD = 0x20001
    STOP_RECORD  = 0x20002
    START_PLACE  = 0x20003
    STOP_PLACE   = 0x20004
    KEEPALIVE    = 0x2000F

PACKET_SIZE = 30
VERSION     = 1

# ── models ────────────────────────────────────────────────────────────────────
class DVRRequest(BaseModel):
    gmcode: str = Field(..., description="Game code, e.g. ROUND01 or HEARTBEAT")
    table:  str = Field(..., max_length=4)
    dvr_ip: str = Field(..., description="DVR target IP, e.g. 10.146.11.92")
    dvr_port: int = Field(..., description="DVR target port, e.g. 11007")

class DVRResponse(BaseModel):
    ok:     bool
    gmcode: str
    table:  str
    ret:    int

# ── socket logic ──────────────────────────────────────────────────────────────
async def _handle(cmd: Cmd, req: DVRRequest) -> DVRResponse:
    """Send one command, wait for one 30-byte reply, parse, return."""
    pkt = struct.pack(
        "!I I H 4s 16s",
        cmd,
        PACKET_SIZE,
        VERSION,
        req.table.encode().ljust(4, b"\0"),
        req.gmcode.encode().ljust(16, b"\0"),
    )
    logger.info(
        f"→ {req.dvr_ip}:{req.dvr_port} cmd=0x{cmd:05X} "
        f"table={req.table} gmcode={req.gmcode}"
    )
    reader, writer = await asyncio.open_connection(req.dvr_ip, req.dvr_port)
    writer.write(pkt)
    await writer.drain()

    # ------- 2. recv & parse ----------------------------------------------
    resp = await reader.readexactly(PACKET_SIZE)
    writer.close(); await writer.wait_closed()
    logger.info(f"← raw {resp}")

    cmd_r, size, ver = struct.unpack("!I I H", resp[:10])
    gmcode = resp[10:26].rstrip(b"\0").decode()
    ret    = struct.unpack("!H", resp[28:30])[0]
    ok     = (ret == 0)

    return DVRResponse(ok=ok, gmcode=gmcode, table=req.table, ret=ret)

async def send_keepalive():
    while True:
        try:
            await _handle(Cmd.KEEPALIVE, DVRRequest(gmcode="HEARTBEAT", table="T032", dvr_ip=DVR_TARGET_IP, dvr_port=DVR_TARGET_PORT))
        except Exception as e:
            logger.warning(f"keep-alive failed: {e}")
        await asyncio.sleep(60)

# ── FastAPI setup ─────────────────────────────────────────────────────────────
app = FastAPI(title="DVR-Gateway", version="1.0")

@app.on_event("startup")
async def _startup():
    asyncio.create_task(send_keepalive())

@app.post("/record/{action}", response_model=DVRResponse)
async def record_post(action: Literal["start", "stop"], req: DVRRequest):
    return await _handle(Cmd[f"{action.upper()}_RECORD"], req)

@app.post("/place/{action}", response_model=DVRResponse)
async def place_post(action: Literal["start", "stop"], req: DVRRequest):
    return await _handle(Cmd[f"{action.upper()}_PLACE"], req)

@app.post("/keepalive", response_model=DVRResponse)
async def keepalive_post(req: DVRRequest):
    return await _handle(Cmd.KEEPALIVE, req)

@app.get("/record/{action}", response_model=DVRResponse)
async def record_get(
    action: Literal["start", "stop"],
    gmcode: str = Query("ROUND001"),
    table: str = Query("T032"),
    dvr_ip: str = Query(DVR_TARGET_IP),
    dvr_port: int = Query(DVR_TARGET_PORT),
):
    req = DVRRequest(gmcode=gmcode, table=table, dvr_ip=dvr_ip, dvr_port=dvr_port)
    return await _handle(Cmd[f"{action.upper()}_RECORD"], req)

@app.get("/place/{action}", response_model=DVRResponse)
async def place_get(
    action: Literal["start", "stop"],
    gmcode: str = Query("ROUND001"),
    table: str = Query("T032"),
    dvr_ip: str = Query(DVR_TARGET_IP),
    dvr_port: int = Query(DVR_TARGET_PORT),
):
    req = DVRRequest(gmcode=gmcode, table=table, dvr_ip=dvr_ip, dvr_port=dvr_port)
    return await _handle(Cmd[f"{action.upper()}_PLACE"], req)

@app.get("/keepalive", response_model=DVRResponse)
async def keepalive_get(
    gmcode: str = Query(...),
    table: str = Query(...),
    dvr_ip: str = Query(DVR_TARGET_IP),
    dvr_port: int = Query(DVR_TARGET_PORT),
):
    req = DVRRequest(gmcode=gmcode, table=table, dvr_ip=dvr_ip, dvr_port=dvr_port)
    return await _handle(Cmd.KEEPALIVE, req)


from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

@app.on_event("startup")
async def setup_static_docs():
    # Try local ./static first, then fallback to ../static
    local_static = ROOT / "static"
    fallback_static = ROOT.parent / "static"

    if local_static.exists():
        app.mount("/static", StaticFiles(directory=local_static), name="static")
        logger.info("[docs] Mounted /static from ROOT/static")
    elif fallback_static.exists():
        app.mount("/static", StaticFiles(directory=fallback_static), name="static")
        logger.info("[docs] Mounted /static from ROOT.parent/static")
    else:
        logger.warning("[docs] ⚠ static folder not found in current or parent folder")

    @app.get("/doc", include_in_schema=False)
    async def custom_swagger_docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Swagger UI (Offline)",
            swagger_js_url="/static/swagger/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger/swagger-ui.css",
        )

from common.scramble_utils import decode_payload
AUTH_TOKEN = os.environ["AUTH_TOKEN"]

@app.api_route("/d", methods=["GET", "POST"])
async def dvr_entry(request: Request, p: Optional[str] = None, t: Optional[str] = None):
    if request.method == "POST":
        body = await request.json()
        p = p or body.get("p")
        t = t or body.get("t")
    if t != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")
    data = decode_payload(p)

    route = data.pop("route")      # "record" | "place"
    action = data.pop("action")    # "start"  | "stop"
    cmd = Cmd[f"{action.upper()}_{route.upper()}"]   # enum lookup

    req = DVRRequest(**data)
    return await _handle(cmd, req)
