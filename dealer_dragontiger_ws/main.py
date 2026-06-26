import asyncio
import os
import logging
import tkinter as tk
from datetime import datetime

# ✅ Load .env BEFORE importing modules that may read env on import
from dotenv import load_dotenv
load_dotenv()

from dealer_dragontiger_ws.gui       import DealerGUI
from dealer_dragontiger_ws.tcp_proto import MockDealerAppProtocol
from dealer_dragontiger_ws.ws_proto  import WSDealerProto
from dealer_dragontiger_ws import dvr_client

# ---- logging: file + console -------------------------------------------------
log_filename = f"DT_WS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
handlers = [
    logging.FileHandler(log_filename, encoding="utf-8"),
    logging.StreamHandler()
]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=handlers,
)
log = logging.getLogger("DTMain")
log.info("Logging to %s", log_filename)

PD_HOST  = os.getenv("PYDEALER_HOST", "0.0.0.0")
PD_PORT  = int(os.getenv("PYDEALER_PORT", 2331))
DVR_IP   = os.getenv("DVR_IP",  "127.0.0.1")
DVR_PORT = int(os.getenv("DVR_PORT", 11007))
WS_HOST = os.getenv("WS_HOST")
WS_PORT = os.getenv("WS_PORT")


class StartUI:
    """Small startup window to select:
    - App mode: BAC / DT Dragonpoker / Latency
    - Detector connection: TCP / WS / BOTH

    NOTE: Use checkbox-style selectors (empty by default) but enforce single-selection.
    """

    def __init__(self):
        self.choice = None

        self.root = tk.Tk()
        self.root.title("Mock Dealer App – Start")

        # layout
        pad = {"padx": 10, "pady": 6}
        top = tk.Frame(self.root); top.pack(**pad)

        # App mode group
        app_box = tk.LabelFrame(top, text="App mode"); app_box.pack(side=tk.LEFT, padx=8, pady=8)
        self.app_mode = tk.StringVar(value="")  # start empty
        self._app_vars = {}
        for txt, val in (("BAC", "bac"), ("DT Dragonpoker", "dt"), ("Latency", "latency")):
            v = tk.IntVar(value=0)
            self._app_vars[val] = v
            tk.Checkbutton(
                app_box,
                text=txt,
                variable=v,
                onvalue=1,
                offvalue=0,
                command=lambda vv=val: self._select_app(vv),
            ).pack(anchor="w")

        # Detector connection group
        conn_box = tk.LabelFrame(top, text="Detector connection"); conn_box.pack(side=tk.LEFT, padx=8, pady=8)
        self.conn_mode = tk.StringVar(value="")  # start empty
        self._conn_vars = {}
        for txt, val in (("TCP", "tcp"), ("WS", "ws"), ("BOTH", "both")):
            v = tk.IntVar(value=0)
            self._conn_vars[val] = v
            tk.Checkbutton(
                conn_box,
                text=txt,
                variable=v,
                onvalue=1,
                offvalue=0,
                command=lambda vv=val: self._select_conn(vv),
            ).pack(anchor="w")

        # footer info row
        info = tk.Frame(self.root); info.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(
            info,
            text=f"TCP: {PD_HOST}:{PD_PORT}    WS: {WS_HOST}:{WS_PORT}    DVR: {DVR_IP}:{DVR_PORT}",
            fg="gray30",
        ).pack(anchor="w")

        # Start button
        btn_row = tk.Frame(self.root); btn_row.pack(fill="x", padx=10, pady=(0, 10))
        self.btn_start = tk.Button(btn_row, text="Start", command=self._start, state="disabled", width=12)
        self.btn_start.pack(side=tk.RIGHT)

        # Close behavior
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _select_app(self, selected: str):
        # Enforce single-selection; allow toggling off.
        if self._app_vars[selected].get() == 1:
            for k, v in self._app_vars.items():
                if k != selected:
                    v.set(0)
            self.app_mode.set(selected)
        else:
            self.app_mode.set("")
        self._update_start_btn()

    def _select_conn(self, selected: str):
        # Enforce single-selection; allow toggling off.
        if self._conn_vars[selected].get() == 1:
            for k, v in self._conn_vars.items():
                if k != selected:
                    v.set(0)
            self.conn_mode.set(selected)
        else:
            self.conn_mode.set("")
        self._update_start_btn()

    def _update_start_btn(self):
        ok = bool(self.app_mode.get().strip()) and bool(self.conn_mode.get().strip())
        self.btn_start.config(state=("normal" if ok else "disabled"))

    def _start(self):
        self.choice = (self.app_mode.get().strip(), self.conn_mode.get().strip())
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_close(self):
        # user closed the window; exit
        self.choice = None
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()
        return self.choice


class DragonTigerApp:
    def __init__(self, ui_mode: str = "bac", conn_mode: str = "tcp"):
        # ui_mode: "bac" / "dt" / "latency"
        self.ui_mode = (ui_mode or "bac").lower().strip()
        self._startup_conn_mode = (conn_mode or "").lower().strip()

        # slot count mapping (only affects how many indices/cards the UI shows and DT-auto expects)
        if self.ui_mode == "latency":
            self.max_slots = 1
        elif self.ui_mode == "dt":
            self.max_slots = 3
        else:
            self.max_slots = 6  # bac

        self.predicting    = False
        self.proto_tcp     = None
        self.proto_ws      = None
        self.dvr_proto     = None
        self._mode_locked  = False
        self.use_dvr       = True

        self.gm_base   = datetime.now().strftime("DT%Y%m%d")
        self.gm_seq    = 0
        self.gm_active = None
        self._ready_to_dispatch = False

        self.root = tk.Tk()
        self.gui  = DealerGUI(
            self.root,
            on_start_pred   = self.start_prediction,
            on_stop_pred    = self.stop_prediction,
            on_dispatch_idx = self.dispatch_index,
            on_toggle_dvr   = self._on_toggle_dvr,
            on_mode_selected= self._mode_chosen,
            on_save_result  = self.save_result,
            max_slots       = self.max_slots,
        )

        # Preselect connection mode from the startup UI, then auto-trigger connect.
        if self._startup_conn_mode in ("tcp", "ws", "both"):
            try:
                self.gui.mode_var.set(self._startup_conn_mode)
            except Exception:
                pass

        self.gui.set_gm_base(self._default_gm_base())
        self.gm_base = self.gui.get_gm_base() or self._default_gm_base()

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.root.after(100, self._poll_loop, self.loop)

        self._tcp_task = None
        self._ws_task  = None

        # IMPORTANT: trigger connect immediately if startup selected a mode.
        self.root.after(50, self._mode_chosen)

    def _mode_chosen(self):
        if self._mode_locked: 
            return
        mode = (self.gui.mode_var.get() or "").lower()
        if not mode: 
            return

        if mode in ("tcp", "both"):
            self._tcp_task = self.loop.create_task(self._start_tcp_listener())
            self.gui.set_status(f"Connecting via {mode.upper()} … PD_IP : {PD_HOST}:{PD_PORT}", color="blue")
            log.info("Connecting TCP on %s:%s", PD_HOST, PD_PORT)

        if mode in ("ws", "both"):
            self._ws_task  = self.loop.create_task(self._start_ws_client())
            self.gui.set_status(f"Connecting via {mode.upper()} … WS_IP : {WS_HOST}:{WS_PORT}", color="blue")
            log.info("Connecting WS to %s:%s", WS_HOST, WS_PORT)

        self.gui.lock_mode_selector()
        self._mode_locked = True

    def _default_gm_base(self) -> str:
        return datetime.now().strftime("DT%Y%m%d")

    def _next_gmcode(self) -> str:
        base = (self.gui.get_gm_base() or self.gm_base).strip()
        self.gm_base = base
        self.gm_seq += 1
        self.gm_active = f"{base}_{self.gm_seq}"
        self.gmcode = self.gm_active
        return self.gm_active

    def on_predict_result(self, idx: int, val: int, score: float, gmcode_bytes: bytes | None = None):
        """Unified predict-result handler.

        Key guarantees:
        - Ignore any predict results when no active round (self.predicting == False).
        - Drop stale results whose gmcode (14 bytes) != current active gmcode (first 14 chars).
        - Latency mode uses 3-class one_label ids: 0=cardback, 1=card, 2=empty.
          Only val==1 counts as "complete" in latency mode.
        - DT/BAC mode uses 64-class card ids (0=cardback, 1..63 real cards).
        """
        if not getattr(self, 'predicting', False):
            return

        # ---- gmcode filter (14-byte compare) ----
        if gmcode_bytes:
            try:
                gm_in = gmcode_bytes.split(b'\x00', 1)[0].decode('ascii', 'ignore')
                gm_active = (self.gm_active or getattr(self, 'gmcode', '') or '')
                gm_active14 = gm_active[:14]
                if gm_in and gm_active14 and gm_in != gm_active14:
                    log.info('[DROP] predict_result gm=%s != active=%s (idx=%s val=%s)', gm_in, gm_active14, idx, val)
                    return
            except Exception:
                pass

        # ---- latency special handling ----
        # Latency mode uses 3-class one_label ids:
        #   0 = cardback, 1 = card-present, 2 = empty
        # IMPORTANT: Never decode these via update_card() (DT 64-class mapping), otherwise val=2 becomes C02.
        if (self.ui_mode or '').lower() == 'latency':
            if val == 0:
                self.gui.update_latency_state(idx, 'cardback')
            elif val == 1:
                self.gui.update_latency_state(idx, 'card')
                # NOTE: In latency mode, only "card-present" (val==1) is considered complete.
                self.gui.note_value_detected(idx)
            elif val == 2:
                self.gui.update_latency_state(idx, 'empty')
            else:
                log.warning("[LATENCY] unexpected val=%s (idx=%s score=%.3f) -> ignored", val, idx, float(score))
            return

        # ---- normal DT/BAC ----

        self.gui.update_card(idx, val)


    def start_prediction(self):
        if self.predicting: 
            return
        if not ((self.proto_tcp and getattr(self.proto_tcp, "logged_in", False)) or (self.proto_ws and getattr(self.proto_ws, "logged_in", False))):
            self.gui.set_status("Detector not ready.", color="red")
            return

        self.gmcode = self._next_gmcode()
        self.gui.set_status(f"Round {self.gmcode} ▸ predicting…")
        log.info("Round start: %s (ui_mode=%s)", self.gmcode, self.ui_mode)

        self._ready_to_dispatch = False
        self.predicting = True
        self.gui.disable_start_prediction()

        # clear only visible slots
        for i in range(self.max_slots):
            self.gui.empty_card(i)

        mode = (self.gui.mode_var.get() or "").lower()
        if mode in ("tcp", "both") and self.proto_tcp and getattr(self.proto_tcp, "logged_in", False):
            self.proto_tcp.send_start_predict(self.gmcode)
        if mode in ("ws", "both") and self.proto_ws and getattr(self.proto_ws, "logged_in", False):
            self.loop.create_task(self.proto_ws.send_start_predict(self.gmcode))

        self._ready_to_dispatch = True
        self.gui.on_prediction_started()
        self.gui.enable_dispatch_buttons()
        self.gui.enable_stop_prediction()
        self._start_dvr_record()

    def stop_prediction(self):
        if not self.predicting: 
            return
        gm = self.gm_active or getattr(self, "gmcode", None)
        self.predicting = False
        if self.proto_tcp and getattr(self.proto_tcp, "logged_in", False):
            self.proto_tcp.send_stop_predict(gm)
        if self.proto_ws and getattr(self.proto_ws, "logged_in", False):
            self.loop.create_task(self.proto_ws.send_stop_predict(gm))
        self._stop_dvr_record()
        self.gui.set_status("Prediction stopped.")
        log.info("Round stop: %s", gm)
        self.gui.disable_dispatch_buttons()
        self.gui.enable_start_prediction()

    def dispatch_index(self, idx: int):
        if not ((self.proto_tcp and getattr(self.proto_tcp, "logged_in", False)) or (self.proto_ws and getattr(self.proto_ws, "logged_in", False))):
            self.gui.set_status("Detector not ready.", color="red")
            return
        if self.proto_tcp and getattr(self.proto_tcp, "logged_in", False):
            self.proto_tcp.send_dispatch_index(getattr(self, "gmcode", ""), idx)
        if self.proto_ws and getattr(self.proto_ws, "logged_in", False):
            self.loop.create_task(self.proto_ws.send_dispatch_index(getattr(self, "gmcode", ""), idx))
        self.gui.set_status(f"Dispatched index {idx}")
        log.info("Dispatch idx=%d gm=%s", idx, getattr(self, "gmcode", ""))

    def save_result(self):
        gm = self.gm_active or getattr(self, "gmcode", None)
        if not self.predicting:
            self.gui.set_status("Cannot save — no active round.", color="red")
            return
        sent = False
        if self.proto_tcp and getattr(self.proto_tcp, "logged_in", False):
            self.proto_tcp.send_save_result(gm); sent = True
        if self.proto_ws and getattr(self.proto_ws, "logged_in", False):
            self.loop.create_task(self.proto_ws.send_save_result(gm)); sent = True
        self.gui.set_status(f"SaveResult sent: {gm}" if sent else "Detector not ready.",
                            color=None if sent else "red")
        if sent: 
            log.info("SaveResult requested: %s", gm)

    def _on_toggle_dvr(self, enabled: bool) -> None:
        self.use_dvr = bool(enabled)
        if not self.use_dvr:
            try: 
                self._stop_dvr_record()
            except Exception: 
                pass
            self.dvr_proto = None
            self.gui.set_status("DVR disabled; will not record.", color="orange")
        else:
            self.gui.set_status("DVR enabled.", color="orange")
        log.info("DVR %s", "ENABLED" if self.use_dvr else "DISABLED")

    def _ensure_dvr(self):
        if not self.use_dvr: 
            return None
        if self.dvr_proto: 
            return self.dvr_proto
        try:
            self.dvr_proto = dvr_client.connect_to_dvr(DVR_IP, DVR_PORT, loop=self.loop)
            log.info("[DVR] connected to %s:%s", DVR_IP, DVR_PORT)
        except Exception as e:
            log.warning("[DVR] connect failed: %s", e)
            self.dvr_proto = None
        return self.dvr_proto

    def _start_dvr_record(self):
        if not self.use_dvr: 
            return
        proto = self._ensure_dvr()
        if proto:
            try:
                proto.send_dvr_command(dvr_client.START_RECORD, table="T032", gmcode=getattr(self, "gmcode", ""))
            except Exception as e:
                log.warning("[DVR] START_RECORD error: %s", e)

    def _stop_dvr_record(self):
        if self.dvr_proto:
            try:
                self.dvr_proto.send_dvr_command(dvr_client.STOP_RECORD, table="T032", gmcode=getattr(self, "gmcode", ""))
            except Exception as e:
                log.warning("[DVR] STOP_RECORD error: %s", e)

    async def _start_tcp_listener(self):
        srv = await self.loop.create_server(lambda: MockDealerAppProtocol(self), PD_HOST, PD_PORT)
        log.info("[Dealer] TCP listening on %s:%s", PD_HOST, PD_PORT)
        async with srv:
            await srv.serve_forever()

    async def _start_ws_client(self):
        self.proto_ws = WSDealerProto(self)
        try:
            await self.proto_ws.connect()
        except Exception as e:
            log.warning("WS connect failed: %s", e)

    def _poll_loop(self, loop):
        loop.call_soon(loop.stop)
        loop.run_forever()
        self.root.after(100, self._poll_loop, loop)

    def run(self):
        self.root.mainloop()


def main():
    # Start UI selection → run dealer UI
    chooser = StartUI()
    choice = chooser.run()
    if not choice:
        return
    ui_mode, conn_mode = choice
    DragonTigerApp(ui_mode=ui_mode, conn_mode=conn_mode).run()


if __name__ == "__main__":
    main()
