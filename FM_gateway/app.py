"""
FM_gateway/app.py
──────────────────
FastAPI application that forwards GET/POST to FieldManager via httpx.
Routes:
- /api/forward_inputjson
- /api/forward_scene_switch
"""

from pathlib import Path
import sys, os
from dotenv import load_dotenv
import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Body
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field
from utils.logging_utils import init_logger

# ── env + path setup ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)

FM_TARGET_IP   = os.environ["FM_TARGET_IP"]
FM_TARGET_PORT = int(os.environ["FM_TARGET_PORT"])

# ── logger ───────────────────────────────────────────────────────────────────
logger = init_logger("fm_gateway_http")
logger.info(f"[fm_gateway] 🎯 Target is {FM_TARGET_IP}:{FM_TARGET_PORT}")

# ── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI(title="FM Gateway", version="1.0")

# ── Pydantic Models (POST) ───────────────────────────────────────────────────
class InputJsonBody(BaseModel):
    devId: str = Field(..., description="Device ID", example="obs")
    streamId: str = Field(..., description="Stream ID", example="OBS233jk")
    tableId: str = Field(..., description="Table ID", example="B002")
    inputName: str = Field(..., description="Input name JSON", example="{header:json,body:[card_index:1,3,4,5,6],sceneName:Near}")

class SceneSwitchBody(BaseModel):
    devId: str = Field(..., description="Device ID", example="obs")
    streamId: str = Field(..., description="Stream ID", example="OBS233jk")
    tableId: str = Field(..., description="Table ID", example="B002")
    sceneName: str = Field(..., description="Scene name", example="Far")

# ── GET + POST: /api/forward_inputjson ───────────────────────────────────────
@app.get("/api/forward_inputjson")
async def forward_inputjson_get(
    devId: str = Query("obs"),
    streamId: str = Query("OBS233jk"),
    tableId: str = Query("B002"),
    inputName: str = Query(
        "{header:json,body:[card_index:1,3,4,5,6],sceneName:Near}",
        description="Input name JSON"
    )
):
    logger.info(f"[FM_GATEWAY] Received GET inputjson: devId={devId}, streamId={streamId}, tableId={tableId}, inputName={inputName}")
    return await forward_inputjson_common(devId, streamId, tableId, inputName)

@app.post("/api/forward_inputjson")
async def forward_inputjson_post(body: InputJsonBody):
    logger.info(f"[FM_GATEWAY] Received POST inputjson: {body}")
    return await forward_inputjson_common(body.devId, body.streamId, body.tableId, body.inputName)

async def forward_inputjson_common(devId, streamId, tableId, inputName):
    url = f"http://{FM_TARGET_IP}:{FM_TARGET_PORT}/test/{devId}/inputjson/"
    params = {
        "devId": devId,
        "streamId": streamId,
        "tableId": tableId,
        "inputName": inputName
    }
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"[FM_GATEWAY] → GET {url} with params={params}")
            resp = await client.get(url, params=params)
            logger.info(f"[FM_GATEWAY] ← Status {resp.status_code} Response: {resp.text}")
            return resp.text
    except Exception as e:
        logger.error(f"[FM_GATEWAY] inputjson forwarding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── GET + POST: /api/forward_scene_switch ────────────────────────────────────
@app.get("/api/forward_scene_switch")
async def forward_scene_switch_get(
    devId: str = Query("obs"),
    streamId: str = Query("OBS233jk"),
    tableId: str = Query("B002"),
    sceneName: str = Query("Far", description="Scene name")
):
    logger.info(f"[FM_GATEWAY] Received GET scene_switch: devId={devId}, streamId={streamId}, tableId={tableId}, sceneName={sceneName}")
    return await forward_scene_common(devId, streamId, tableId, sceneName)

@app.post("/api/forward_scene_switch")
async def forward_scene_switch_post(body: SceneSwitchBody):
    logger.info(f"[FM_GATEWAY] Received POST scene_switch: {body}")
    return await forward_scene_common(body.devId, body.streamId, body.tableId, body.sceneName)

async def forward_scene_common(devId, streamId, tableId, sceneName):
    url = f"http://{FM_TARGET_IP}:{FM_TARGET_PORT}/test/{devId}/scene/"
    params = {
        "devId": devId,
        "streamId": streamId,
        "tableId": tableId,
        "sceneName": sceneName
    }
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"[FM_GATEWAY] → GET {url} with params={params}")
            resp = await client.get(url, params=params)
            logger.info(f"[FM_GATEWAY] ← Status {resp.status_code} Response: {resp.text}")
            return resp.text
    except Exception as e:
        logger.error(f"[FM_GATEWAY] scene_switch forwarding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Swagger UI (Offline) ──────────────────────────────────────────────────────
@app.on_event("startup")
async def setup_static_docs():
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

@app.api_route("/v", methods=["GET", "POST"])
async def fm_entry(request: Request, p: Optional[str] = None, t: Optional[str] = None):
    if request.method == "POST":
        body = await request.json()
        p = p or body.get("p")
        t = t or body.get("t")

    if t != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

    data = decode_payload(p)
    route = data.pop("route")
    if route == "inputjson":
        return await forward_inputjson_common(
            data["devId"], data["streamId"], data["tableId"], data["inputName"]
        )
    elif route == "scene":
        return await forward_scene_common(
            data["devId"], data["streamId"], data["tableId"], data["sceneName"]
        )
    else:
        raise HTTPException(status_code=400, detail="unknown route")