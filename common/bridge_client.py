from __future__ import annotations
import httpx

BRIDGE_PORT = 8080

class DVRBridgeClient:
    """Tiny async wrapper used by the GUI to talk to the bridge."""
    def __init__(self, host: str):
        self.base = f"http://{host}:{BRIDGE_PORT}"
        self.cli  = httpx.AsyncClient(timeout=5)

    async def close(self): await self.cli.aclose()

    async def _post(self, ep: str, gm, table="T032", dvr_ip="127.0.0.1"):
        r = await self.cli.post(
            f"{self.base}{ep}",
            json={"gmcode": gm, "table": table, "dvr_ip": dvr_ip},
        )
        r.raise_for_status()
        return r.json()

    async def start_record(self, g, **kw): return await self._post("/record/start", g, **kw)
    async def stop_record (self, g, **kw): return await self._post("/record/stop" , g, **kw)
    async def start_place (self, g, **kw): return await self._post("/place/start", g, **kw)
    async def stop_place  (self, g, **kw): return await self._post("/place/stop" , g, **kw)
    async def keepalive   (self, g, **kw): return await self._post("/keepalive"  , g, **kw)
