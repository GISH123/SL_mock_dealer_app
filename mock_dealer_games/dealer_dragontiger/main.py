# dealer_dragontiger/main.py
import asyncio, os, sys, logging, tkinter as tk
from datetime import datetime
from dotenv import load_dotenv

from .gui      import DealerGUI
from .protocol import MockDealerAppProtocol
from . import dvr_client                       # unchanged helper

load_dotenv()                                  # .env support
log = logging.getLogger("DTMain")
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                    level=logging.INFO)

# env --------------------------------------------------------------------
PD_HOST  = os.getenv("PYDEALER_HOST", "0.0.0.0")
PD_PORT  = int(os.getenv("PYDEALER_PORT", 2331))
DVR_IP   = os.getenv("DVR_IP",  "127.0.0.1")
DVR_PORT = int(os.getenv("DVR_PORT", 11007))

class DragonTigerApp:
    def __init__(self):
        # state ----------------------------------------------------------
        self.gmcode       = "INIT"
        self.predicting   = False
        self.proto        = None
        self.dvr_proto    = None

        # Tk root + GUI --------------------------------------------------
        self.root = tk.Tk()
        self.gui  = DealerGUI(
            self.root,
            on_start_pred  = self.start_prediction,
            on_stop_pred       = self.stop_prediction,
            on_dispatch_idx    = self.dispatch_index,
            on_save_result  = self.save_result,  
            max_slots          = 6
        )

        # asyncio loop (dedicated) --------------------------------------
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._start_listener())
        self.root.after(100, self._poll_loop, self.loop)

    # --------------------------------------------------------------------

    def start_prediction(self):
        if not self.proto or not self.proto.logged_in or self.predicting:
            return
        # ---- create a new round automatically ----
        self.gmcode = datetime.now().strftime("DG%Y%m%d_%H%M%S")
        self.gui.set_status(f"Round {self.gmcode} – predicting…")
        for i in range(6):
            self.gui.empty_card(i)

        # ---- regular start-prediction steps ----
        self.predicting = True
        self.gui.disable_start_prediction()
        self.proto.send_start_predict(self.gmcode)   

        # enable round behaviors
        self.gui.enable_dispatch_buttons()
        self.gui.enable_stop_prediction()
        self._start_dvr_record()

    def stop_prediction(self):
        if not self.predicting:
            return
        self.predicting = False
        if self.proto and self.proto.logged_in:
            self.proto.send_stop_predict(self.gmcode)
        self._stop_dvr_record()
        self.gui.set_status("Prediction stopped.")
        self.gui.disable_stop_prediction()
        self.gui.disable_dispatch_buttons()
        self.gui.enable_start_prediction()

    def dispatch_index(self, idx: int):
        if not (self.proto and self.proto.logged_in):
            self.gui.set_status("Detector not ready.", color="red")
            return
        self.proto.send_dispatch_index(self.gmcode, idx)
        self.gui.set_status(f"Dispatched index {idx}")

    def save_result(self):
        # ensure we always have the latest textbox/base name logic
        base = self._current_gmcode_base  # whatever you store for the gmcode base
        # current round’s full gmcode string is already in self.gmcode
        gm = self.gmcode or f"{base}_1"

        # send according to selected mode
        sent = False
        if self.mode in ("TCP", "Both") and self.proto_tcp and self.proto_tcp.logged_in:
            self.proto_tcp.send_save_result(gm); sent = True
        if self.mode in ("WS", "Both") and self.proto_ws and self.proto_ws.logged_in:
            # ws version is async
            self.loop.create_task(self.proto_ws.send_save_result(gm)); sent = True

        if sent:
            self.gui.set_status(f"SaveResult sent: {gm}")
        else:
            self.gui.set_status("Detector not ready.", color="red")

    # ---------------- DVR helpers ---------------------------------------
    def _ensure_dvr(self):
        # if self.dvr_proto and not self.dvr_proto.is_closed():
        if self.dvr_proto:
            return self.dvr_proto
        try:
            self.dvr_proto = dvr_client.connect_to_dvr(
                DVR_IP, DVR_PORT, loop=self.loop)
            log.info("[DVR] connected to %s:%s", DVR_IP, DVR_PORT)
        except Exception as e:
            log.warning("[DVR] connect failed: %s", e)
            self.dvr_proto = None
        return self.dvr_proto

    def _start_dvr_record(self):
        proto = self._ensure_dvr()
        if proto:
            try:
                proto.send_dvr_command(
                    dvr_client.START_RECORD, table="T032", gmcode=self.gmcode)
            except Exception as e:
                print("[DVR] START_RECORD error:", e)

    def _stop_dvr_record(self):
        if self.dvr_proto:
            try:
                self.dvr_proto.send_dvr_command(
                    dvr_client.STOP_RECORD, table="T032", gmcode=self.gmcode)
            except Exception as e:
                print("[DVR] STOP_RECORD error:", e)

    # ---------------- detector TCP listener -----------------------------
    async def _start_listener(self):
        srv = await self.loop.create_server(
            lambda: MockDealerAppProtocol(self), PD_HOST, PD_PORT)
        log.info("[Dealer] Listening on %s:%s", PD_HOST, PD_PORT)
        async with srv:
            await srv.serve_forever()

    # ---------------- Tk / asyncio bridge -------------------------------
    def _poll_loop(self, loop):
        loop.call_soon(loop.stop)
        loop.run_forever()
        self.root.after(100, self._poll_loop, loop)

    # ---------------- entry-point ---------------------------------------
    def run(self):
        self.root.mainloop()

def main():
    DragonTigerApp().run()

if __name__ == "__main__":
    main()
