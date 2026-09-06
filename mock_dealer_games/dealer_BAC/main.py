
import asyncio
import json
import logging
import os
import sys
import tkinter as tk
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_runtime import resolve_env_path, runtime_root
from gui import DealerGUI
from tcp_proto import MockDealerAppProtocol
import dvr_client
from dvr_double_packet_test import DVRDoublePacketTestUI

load_dotenv(resolve_env_path(__file__))

LOG_DIR = runtime_root(__file__) / 'logs'
LOG_DIR.mkdir(exist_ok=True)
log_filename = LOG_DIR / f"BAC_HTTP_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
handlers = [logging.FileHandler(log_filename, encoding='utf-8'), logging.StreamHandler()]
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(name)s] %(message)s', handlers=handlers)
log = logging.getLogger('BACMain')
log.info('Logging to %s', str(log_filename))

PD_HOST = os.getenv('PYDEALER_HOST', '0.0.0.0')
PD_PORT = int(os.getenv('PYDEALER_PORT', 2331))
DVR_IP = os.getenv('DVR_IP', '127.0.0.1')
DVR_PORT = int(os.getenv('DVR_PORT', 11007))
HTTP_BASE_URL = os.getenv('HTTP_BASE_URL', 'http://127.0.0.1:1234')
HTTP_TABLE = os.getenv('HTTP_TABLE', 'B004')
HTTP_DEVICE_ID = os.getenv('HTTP_DEVICE_ID', 'obs')
HTTP_STREAM_ID = os.getenv('HTTP_STREAM_ID', 'OBS233jk')
HTTP_TIMEOUT_S = float(os.getenv('HTTP_TIMEOUT_S', '8'))
LOGIN_VID = os.getenv('LOGIN_VID', 'B004')
LOGIN_GMTYPE = os.getenv('LOGIN_GMTYPE', 'BAC')

class BACDealerApp:
    def __init__(self):
        self.predicting = False
        self.proto_tcp = None
        self.dvr_proto = None
        self.listener_started = False
        self._mode_locked = False
        self.use_dvr = False
        self.control_mode = 'tcp'
        self.game_mode = 'dt3'
        self.max_slots = 3
        self.login_vid = LOGIN_VID
        self.login_gmtype = LOGIN_GMTYPE
        self.http_base_url = HTTP_BASE_URL.rstrip('/')
        self.http_table = HTTP_TABLE
        self.http_device_id = HTTP_DEVICE_ID
        self.http_stream_id = HTTP_STREAM_ID
        self.http_timeout_s = HTTP_TIMEOUT_S
        self.gm_base = self._default_gm_base()
        self.gm_seq = 0
        self.gm_active = None
        self.gmcode = None
        self.slot_results = {}
        self._ready_to_dispatch = False

        self.root = tk.Tk()
        self.root.title('Mock Dealer App - BAC')
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.root.after(100, self._poll_loop, self.loop)

        self.gui = None
        self._startup_frame = None
        self._startup_mode_var = tk.StringVar(value='tcp')
        self._startup_dvr_var = tk.BooleanVar(value=False)
        self._startup_game_mode_var = tk.StringVar(value='dt3')
        self._startup_status_var = tk.StringVar(value='Choose control mode, then Confirm.')
        self._build_startup_ui()

    def game_code_4(self) -> bytes:
        return b'BAC'

    def _default_gm_base(self) -> str:
        return datetime.now().strftime('BAC%m%d')

    def _next_gmcode(self) -> str:
        base = (self.gui.get_gm_base() or self.gm_base).strip() if self.gui else self.gm_base
        self.gm_base = base
        self.gm_seq += 1
        self.gm_active = f'{base}_{self.gm_seq}'
        self.gmcode = self.gm_active
        return self.gm_active

    def _mode_chosen(self):
        if self._mode_locked:
            return
        self.control_mode = (self.gui.mode_var.get() or 'tcp').lower()
        if not self.listener_started:
            self.loop.create_task(self._start_tcp_listener())
            self.listener_started = True
        mode_name = 'DT' if self.max_slots == 3 else 'BAC'
        self.gui.set_status(f'{mode_name} dealer connecting | control={self.control_mode.upper()} | TCP listen {PD_HOST}:{PD_PORT} | HTTP {self.http_base_url}', color='blue')
        log.info('Control mode=%s | TCP listener %s:%s | HTTP base=%s', self.control_mode, PD_HOST, PD_PORT, self.http_base_url)
        self.gui.lock_mode_selector()
        self._mode_locked = True

    def send_http_control(self, action: str, gmcode: str, gmstate: int = 0, index: int | None = None):
        payload = {'gmcode': gmcode, 'gmstate': int(gmstate), 'table': self.http_table, 'deviceId': self.http_device_id, 'streamId': self.http_stream_id}
        if index is not None:
            payload['index'] = int(index)
        url = f"{self.http_base_url}/{action.lstrip('/')}"
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=self.http_timeout_s) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
                if index is None:
                    log.info('[HTTP] %s ok gmcode=%s gmstate=%s resp=%s', action, gmcode, gmstate, raw)
                else:
                    log.info('[HTTP] %s ok gmcode=%s index=%s resp=%s', action, gmcode, index, raw)
                return True, raw
        except Exception as e:
            if index is None:
                log.error('[HTTP] %s failed gmcode=%s gmstate=%s err=%s', action, gmcode, gmstate, e)
            else:
                log.error('[HTTP] %s failed gmcode=%s index=%s err=%s', action, gmcode, index, e)
            return False, str(e)

    def start_prediction(self):
        if self.predicting:
            return
        if not (self.proto_tcp and self.proto_tcp.logged_in):
            self.gui.set_status('Detector not ready (TCP login missing).', color='red')
            return
        self.gmcode = self._next_gmcode()
        self.slot_results = {}
        self._ready_to_dispatch = False
        self.predicting = True
        self.gui.set_status(f'Round {self.gmcode} ▸ predicting…')
        log.info('Round start: %s | control=%s', self.gmcode, self.control_mode)
        self.gui.disable_start_prediction()
        for i in range(self.max_slots):
            self.gui.empty_card(i)
        sent = False
        if self.control_mode in ('tcp', 'both'):
            self.proto_tcp.send_start_predict(self.gmcode)
            sent = True
        if self.control_mode in ('http', 'both'):
            ok, _ = self.send_http_control('start_predict', self.gmcode, 2)
            sent = sent or ok
        if not sent:
            self.predicting = False
            self.gui.enable_start_prediction()
            self.gui.set_status('StartPredict failed.', color='red')
            return
        self._ready_to_dispatch = True
        self.gui.on_prediction_started()
        self.gui.enable_dispatch_buttons()
        self.gui.enable_stop_prediction()
        self.gui.enable_cancel_result()
        self._start_dvr_record()

    def stop_prediction(self):
        if not self.predicting:
            return
        gm = self.gm_active or self.gmcode
        self.predicting = False
        if self.control_mode in ('tcp', 'both') and self.proto_tcp and self.proto_tcp.logged_in:
            self.proto_tcp.send_stop_predict(gm)
        if self.control_mode in ('http', 'both'):
            self.send_http_control('stop_predict', gm, 0)
        self._stop_dvr_record()
        self.gui.set_status('Prediction stopped.')
        log.info('Round stop: %s', gm)
        self.gui.disable_dispatch_buttons()
        self.gui.enable_start_prediction()
        self.gui.disable_cancel_result()

    def dispatch_index(self, idx: int):
        idx = int(idx)
        if idx not in (1, 2, 3, 4, 5, 6):
            self.gui.set_status('BAC: only indices 1-6 are allowed.', color='orange')
            return
        if not (self.proto_tcp and self.proto_tcp.logged_in):
            self.gui.set_status('Detector not ready.', color='red')
            return
        gm = self.gm_active or self.gmcode
        sent = False
        if self.control_mode in ('tcp', 'both') and self.proto_tcp and self.proto_tcp.logged_in:
            self.proto_tcp.send_dispatch_index(gm, idx)
            sent = True
        if self.control_mode in ('http', 'both'):
            ok, _ = self.send_http_control('dispatch_index', gm, 0, index=idx)
            sent = sent or ok
        if sent:
            self.gui.set_status(f'Dispatched index {idx}')
            log.info('Dispatch idx=%d gm=%s mode=%s', idx, gm, self.control_mode)
        else:
            self.gui.set_status('Dispatch failed.', color='red')

    def save_result(self):
        gm = self.gm_active or self.gmcode
        if not self.predicting or not gm:
            self.gui.set_status('Cannot save — no active round.', color='red')
            return
        if not (self.proto_tcp and self.proto_tcp.logged_in):
            self.gui.set_status('Detector not ready.', color='red')
            return

        sent = False
        if self.control_mode in ('tcp', 'both'):
            self.proto_tcp.send_save_result(gm)
            sent = True
        if self.control_mode in ('http', 'both'):
            ok, _ = self.send_http_control('save_result', gm, 0)
            sent = sent or ok

        if sent:
            self.gui.set_status(f'SaveResult sent: {gm}')
            log.info('SaveResult requested: %s | mode=%s', gm, self.control_mode)
        else:
            self.gui.set_status('SaveResult failed.', color='red')

    def cancel_result(self):
        gm = self.gm_active or self.gmcode
        if not gm:
            self.gui.set_status('Cannot cancel — no active round.', color='red')
            return
        if self.proto_tcp and self.proto_tcp.logged_in:
            self.proto_tcp.send_cancel_result(gm)
            self.gui.set_status(f'CancelResult sent: {gm}')
            log.info('CancelResult requested: %s', gm)
        else:
            self.gui.set_status('Detector not ready.', color='red')

    def update_slots(self, gmcode: str, results):
        self.gm_active = gmcode or self.gm_active
        pretty = []
        for idx, dealer_classid, score in results:
            self.slot_results[int(idx)] = (int(dealer_classid), float(score))
            self.gui.update_card(int(idx), int(dealer_classid))
            pretty.append(f'idx{idx}={dealer_classid}@{score:.4f}')
        self.gui.on_first_result()
        log.info('PredictResult gmcode=%s %s', gmcode, ', '.join(pretty))

    def _on_toggle_dvr(self, enabled: bool) -> None:
        self.use_dvr = bool(enabled)
        if not self.use_dvr:
            try: self._stop_dvr_record()
            except Exception: pass
            self.dvr_proto = None
            self.gui.set_status('DVR disabled; will not record.', color='orange')
        else:
            self.gui.set_status('DVR enabled.', color='orange')
        log.info('DVR %s', 'ENABLED' if self.use_dvr else 'DISABLED')

    def _ensure_dvr(self):
        if not self.use_dvr: return None
        if self.dvr_proto: return self.dvr_proto
        try:
            self.dvr_proto = dvr_client.connect_to_dvr(DVR_IP, DVR_PORT, loop=self.loop)
            log.info('[DVR] connected to %s:%s', DVR_IP, DVR_PORT)
        except Exception as e:
            log.warning('[DVR] connect failed: %s', e)
            self.dvr_proto = None
        return self.dvr_proto

    def _start_dvr_record(self):
        if not self.use_dvr: return
        proto = self._ensure_dvr()
        if proto:
            try: proto.send_dvr_command(dvr_client.START_RECORD, table='T032', gmcode=self.gmcode)
            except Exception as e: log.warning('[DVR] START_RECORD error: %s', e)

    def _stop_dvr_record(self):
        if self.dvr_proto:
            try: self.dvr_proto.send_dvr_command(dvr_client.STOP_RECORD, table='T032', gmcode=self.gmcode)
            except Exception as e: log.warning('[DVR] STOP_RECORD error: %s', e)

    async def _start_tcp_listener(self):
        srv = await self.loop.create_server(lambda: MockDealerAppProtocol(self), PD_HOST, PD_PORT)
        log.info('[Dealer] TCP listening on %s:%s', PD_HOST, PD_PORT)
        async with srv:
            await srv.serve_forever()

    def _poll_loop(self, loop):
        loop.call_soon(loop.stop)
        loop.run_forever()
        self.root.after(100, self._poll_loop, loop)

    def run(self):
        self.root.mainloop()

    def _build_startup_ui(self):
        frm = ttk.Frame(self.root, padding=14)
        frm.pack(fill='both', expand=True)
        self._startup_frame = frm
        ttk.Label(frm, text='Mock Dealer Launcher', font=('Arial', 12, 'bold')).pack(anchor='w')
        ttk.Label(frm, textvariable=self._startup_status_var, foreground='gray').pack(anchor='w', pady=(4, 0))
        ttk.Label(frm, text='(1) Control mode (pick one):').pack(anchor='w', pady=(12, 0))
        row = ttk.Frame(frm)
        row.pack(anchor='w', pady=(6, 0))
        tk.Radiobutton(row, text='TCP', value='tcp', variable=self._startup_mode_var, indicatoron=0, width=8).pack(side='left', padx=(0, 6))
        tk.Radiobutton(row, text='HTTP', value='http', variable=self._startup_mode_var, indicatoron=0, width=8).pack(side='left', padx=(0, 6))
        tk.Radiobutton(row, text='Both', value='both', variable=self._startup_mode_var, indicatoron=0, width=8).pack(side='left')
        ttk.Label(frm, text='(2) Game mode (pick one):').pack(anchor='w', pady=(14, 0))
        row2 = ttk.Frame(frm)
        row2.pack(anchor='w', pady=(6, 0))
        tk.Radiobutton(row2, text='DT (3 slots)', value='dt3', variable=self._startup_game_mode_var, indicatoron=0, width=16).pack(side='left', padx=(0, 6))
        tk.Radiobutton(row2, text='BAC Classic (6 slots)', value='bac6', variable=self._startup_game_mode_var, indicatoron=0, width=18).pack(side='left')
        row2b = ttk.Frame(frm)
        row2b.pack(anchor='w', pady=(6, 0))
        tk.Radiobutton(row2b, text='DVR Double Packet Test', value='dvr_double', variable=self._startup_game_mode_var, indicatoron=0, width=24).pack(side='left')
        row3 = ttk.Frame(frm)
        row3.pack(anchor='w', pady=(12, 0))
        ttk.Checkbutton(row3, text='Enable DVR', variable=self._startup_dvr_var).pack(side='left')
        ttk.Label(frm, text=f'TCP listen: {PD_HOST}:{PD_PORT} | HTTP base: {self.http_base_url}', foreground='gray').pack(anchor='w', pady=(8, 0))
        ttk.Button(frm, text='Confirm', command=self._on_startup_confirm).pack(anchor='e', pady=(14, 0))

    def _on_startup_confirm(self):
        self.control_mode = (self._startup_mode_var.get() or 'tcp').strip().lower()
        self.game_mode = (self._startup_game_mode_var.get() or 'dt3').strip().lower()
        if self.game_mode == 'dvr_double':
            self.use_dvr = False
            if self._startup_frame is not None:
                self._startup_frame.destroy()
                self._startup_frame = None
            self._dvr_double_test_ui = DVRDoublePacketTestUI(
                self.root, default_ip=DVR_IP, default_port=DVR_PORT
            )
            return
        self.max_slots = 6 if self.game_mode == 'bac6' else 3
        self.use_dvr = bool(self._startup_dvr_var.get())
        if self._startup_frame is not None:
            self._startup_frame.destroy()
            self._startup_frame = None
        self.gui = DealerGUI(self.root, on_start_pred=self.start_prediction, on_stop_pred=self.stop_prediction, on_dispatch_idx=self.dispatch_index, on_toggle_dvr=self._on_toggle_dvr, on_mode_selected=self._mode_chosen, on_save_result=self.save_result, on_cancel_result=self.cancel_result, max_slots=self.max_slots, on_toggle_latency=None)
        try:
            self.root.title('Mock Dealer App - DT' if self.max_slots == 3 else 'Mock Dealer App - BAC Classic')
        except Exception:
            pass
        try: self.gui.dvr_var.set(self.use_dvr)
        except Exception: pass
        self._on_toggle_dvr(self.use_dvr)
        self.gui.mode_var.set(self.control_mode)
        self._apply_game_mode_ui()
        self.gm_base = self._default_gm_base()
        self.gm_seq = 0
        self.gm_active = None
        self.gmcode = None
        self.gui.set_gm_base(self.gm_base)
        self._mode_chosen()
        # Dispatch All default for DT is handled inside DealerGUI persistence loading:
        # respect last_save_default_gap_value.env/.env when present, otherwise DT falls back to 0.3s.

    def _apply_game_mode_ui(self):
        if self.gui is None: return
        try: self.gui.set_latency_mode(False)
        except Exception: pass
        game_label = 'DT' if self.max_slots == 3 else 'BAC Classic'
        try: self.gui.set_mode_banner(f'🎮 {game_label} | 🔌 {self.control_mode.upper()} | 🧩 slots={self.max_slots}')
        except Exception: pass
        if hasattr(self.gui, 'btn_latency_mode') and self.gui.btn_latency_mode is not None:
            try: self.gui.btn_latency_mode.pack_forget()
            except Exception: pass
        ready_label = 'DT 3-slot mode ready.' if self.max_slots == 3 else 'BAC classic 6-slot mode ready.'
        self.gui.set_status(ready_label, color='orange')


def main():
    app = BACDealerApp()
    app.run()

if __name__ == '__main__':
    main()
