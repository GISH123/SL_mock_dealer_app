from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

@app.get("/test/{devId}/inputjson/")
async def get_inputjson(devId: str, streamId: str, tableId: str, inputName: str):
    print(f"[MockFM][GET /test/{devId}/inputjson/] devId={devId}, streamId={streamId}, tableId={tableId}, inputName={inputName}")
    return {"status": "received", "via": "GET", "devId": devId}

@app.post("/test/{devId}/inputjson/")
async def post_inputjson(devId: str, req: Request):
    data = await req.json()
    print(f"[MockFM][POST /test/{devId}/inputjson/] devId={devId} payload={data}")
    return {"status": "received", "via": "POST", "devId": devId, **data}

@app.get("/test/{devId}/scene/")
async def get_scene(devId: str, streamId: str, tableId: str, sceneName: str):
    print(f"[MockFM][GET /test/{devId}/scene/] devId={devId}, streamId={streamId}, tableId={tableId}, sceneName={sceneName}")
    return {"status": "received", "via": "GET", "devId": devId}

@app.post("/test/{devId}/scene/")
async def post_scene(devId: str, req: Request):
    data = await req.json()
    print(f"[MockFM][POST /test/{devId}/scene/] devId={devId} payload={data}")
    return {"status": "received", "via": "POST", "devId": devId, **data}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081, reload=False)
