import asyncio
import struct
import tkinter as tk
from tkinter import scrolledtext, Button, Frame, Label
from datetime import datetime
import os
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import logging
from logging.handlers import TimedRotatingFileHandler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared_runtime import UILogMirror, instance_timestamp_log_path, resolve_card_pack_dir, runtime_root

########################################
# Detector-Side Commands (must match pydealerclientlight/cardmsg.py)
########################################
CMD_LOGIN          = 0xAB0002
CMD_LOGIN_R        = 0xBA0002
CMD_START_PREDICT  = 0xBA0003
CMD_PREDICT_RESULT = 0xAB0004
CMD_KEEPALIVE      = 0xAB0001
CMD_STOP_PREDICT   = 0xBA0004


def _rank_label(v):
    """BALL3 wheel label mapping."""
    try:
        v = int(v)
    except Exception:
        return str(v)
    if v == 1:
        return 'A'
    if v == 11:
        return 'J'
    if v == 12:
        return 'Q'
    if v == 13:
        return 'K'
    return str(v)


def _rank_int(v):
    """Convert rank label/int into int code expected by wheel mapping."""
    if isinstance(v, int):
        return v
    try:
        s = str(v).strip().upper()
    except Exception:
        return 0
    if s.isdigit():
        return int(s)
    face = {'A': 1, 'J': 11, 'Q': 12, 'K': 13}
    return face.get(s, 0)


class WheelCanvas:
    """A simple BALL3 wheel visualization.

    Layout (clockwise): J, Q, K, 10, 9, A
    Shown positions (as your guide):
             Q
        J         K
        A    9    10
    """

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        # Draw an oval/perspective wheel similar to the in-game bowl.
        self.size = 520
        self.cx = self.size // 2
        self.cy = self.size // 2
        # Outer bowl radii (ellipse)
        self.rx = 215
        self.ry = 160
        self.canvas = tk.Canvas(parent, width=self.size, height=self.size, bg='white', highlightthickness=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Sector center angles (Tk angles: 0 at 3 o'clock, positive CCW)
        # Tuned to look like the screenshot.
        self.rank_angle = {
            13: 90,    # K (top)
            10: 25,    # 10 (upper-right)
            9: 330,    # 9 (lower-right)
            1: 270,    # A (bottom)
            11: 210,   # J (lower-left)
            12: 150,   # Q (upper-left)
        }

        # Precompute label positions and ball positions separately.
        # Labels are a bit more outward; balls are more inward so they don't cover text.
        self.rank_label_pos = {}
        self.rank_ball_pos = {}
        import math
        for code, ang in self.rank_angle.items():
            rad = math.radians(ang)

            # label: slightly outward
            lx = self.cx + int((self.rx * 0.68) * math.cos(rad))
            ly = self.cy - int((self.ry * 0.68) * math.sin(rad))
            self.rank_label_pos[code] = (lx, ly)

            # ball: more inward (put it on the colored inner wheel, not on the dark ring)
            bx = self.cx + int((self.rx * 0.40) * math.cos(rad))
            by = self.cy - int((self.ry * 0.40) * math.sin(rad))
            self.rank_ball_pos[code] = (bx, by)

        # Optional card images
        self.images = {}
        self._load_images()

        # Drawing ids
        self._ball_ids = []
        self._label_ids = []
        self._draw_static()

    def _load_images(self):
        """Load PNG images from local or parent-root card_shown_ui if available."""
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, 'card_shown_ui'),
            os.path.join(os.path.dirname(base_dir), 'card_shown_ui'),
        ]
        img_dir = next((p for p in candidates if os.path.isdir(p)), None)
        if not img_dir:
            return

        # Tk PhotoImage supports PNG on most Windows Python builds.
        name_map = {
            'A': 'A.png',
            '9': '9.png',
            '10': '10.png',
            'J': 'J.png',
            'Q': 'Q.png',
            'K': 'K.png',
        }
        for k, fn in name_map.items():
            p = os.path.join(img_dir, fn)
            if os.path.isfile(p):
                try:
                    self.images[k] = tk.PhotoImage(file=p)
                except Exception:
                    pass

    def _draw_static(self):
        self.canvas.delete('all')
        # ----- Bowl rings (approximate the in-game look) -----
        def oval(rx, ry, **kw):
            return self.canvas.create_oval(self.cx - rx, self.cy - ry, self.cx + rx, self.cy + ry, **kw)

        # outer lip
        oval(self.rx, self.ry, outline='#2f6ea7', width=6, fill='#6db0e3')
        # inner lip
        oval(int(self.rx*0.92), int(self.ry*0.92), outline='#d7eefc', width=8, fill='#a7d7f5')
        # stepped rings
        oval(int(self.rx*0.82), int(self.ry*0.82), outline='#f3fbff', width=6, fill='#e8f7ff')
        oval(int(self.rx*0.74), int(self.ry*0.74), outline='#cfeaf8', width=6, fill='#dff3ff')
        oval(int(self.rx*0.66), int(self.ry*0.66), outline='#f3fbff', width=6, fill='#e8f7ff')

        # dark blue ring with "bolts"
        oval(int(self.rx*0.56), int(self.ry*0.56), outline='#0b2b52', width=10, fill='#0e3a6c')

        # bolts
        import math
        bolt_rx = int(self.rx*0.53)
        bolt_ry = int(self.ry*0.53)
        for i in range(10):
            ang = math.radians(20 + i * 32)
            x = self.cx + int(bolt_rx * math.cos(ang))
            y = self.cy - int(bolt_ry * math.sin(ang))
            self.canvas.create_oval(x-3, y-3, x+3, y+3, outline='#c7d5e3', fill='#9fb3c6', width=1)

        # ----- Inner wheel sectors -----
        inner_rx = int(self.rx * 0.46)
        inner_ry = int(self.ry * 0.46)
        bbox = (self.cx - inner_rx, self.cy - inner_ry, self.cx + inner_rx, self.cy + inner_ry)

        # Sector colors (roughly matching screenshot vibes)
        colors = {
            11: '#67c46b',  # J green
            12: '#ff6b6b',  # Q red
            13: '#e7d7b6',  # K beige
            10: '#ff9d4d',  # 10 orange
            9:  '#6aa9ff',  # 9 blue
            1:  '#b795ff',  # A purple
        }

        # Draw six 60-degree wedges centered at our tuned angles
        for code, center_ang in self.rank_angle.items():
            start = center_ang - 30
            self.canvas.create_arc(
                *bbox,
                start=start,
                extent=60,
                style=tk.PIESLICE,
                outline='white',
                width=2,
                fill=colors.get(code, '#dddddd')
            )

        # center hub / diamond
        hub_rx = int(self.rx * 0.14)
        hub_ry = int(self.ry * 0.14)
        oval(hub_rx, hub_ry, outline='#91a7bd', width=2, fill='#cdd7e3')
        self.canvas.create_polygon(
            self.cx, self.cy - hub_ry,
            self.cx + hub_rx, self.cy,
            self.cx, self.cy + hub_ry,
            self.cx - hub_rx, self.cy,
            outline='#6c7f93', fill='#a8b6c7', width=2
        )

        # Labels on sectors (or images)
        for code, (x, y) in self.rank_label_pos.items():
            lab = _rank_label(code)
            if lab in self.images:
                img = self.images[lab]
                self._label_ids.append(self.canvas.create_image(x, y, image=img))
            else:
                self._label_ids.append(
                    self.canvas.create_text(x, y, text=lab, font=('Arial', 20, 'bold'), fill='black')
                )

    def clear_balls(self):
        for bid in self._ball_ids:
            try:
                self.canvas.delete(bid)
            except Exception:
                pass
        self._ball_ids = []

    def set_balls(self, ranks):
        """ranks: list[int]"""
        self.clear_balls()
        # If multiple balls land same sector, offset them slightly.
        seen = {}
        for r in ranks:
            r = _rank_int(r)
            if r not in self.rank_ball_pos:
                continue
            x, y = self.rank_ball_pos[r]
            k = seen.get(r, 0)
            seen[r] = k + 1
            # When multiple balls fall into the same sector, offset slightly
            dx = (k % 2) * 18 - 9
            dy = (k // 2) * 18
            # Bigger balls for readability (2x)
            rr = 16
            bid = self.canvas.create_oval(x - rr + dx, y - rr + dy, x + rr + dx, y + rr + dy,
                                          outline='black', width=2, fill='white')
            self._ball_ids.append(bid)


class MockDealerBall3Protocol(asyncio.Protocol):
    """Protocol for communications with the PyDealerClientLight (detector side)."""

    def __init__(self, app):
        self.app = app
        self.transport = None
        self.logged_in = False
        self.game_timestamp = ''  # set by app when starting a round

    def _new_gmcode(self):
        # Deprecated: gmcode/round_id is generated by app.make_round_id()
        return self.app.make_round_id()

    def connection_made(self, transport):
        self.transport = transport
        self.app.protocol = self
        self.app.log('[PyDealer] Connection established.')

    def data_received(self, data):
        if len(data) < 12:
            self.app.log(f'[PyDealer] Received too few bytes: {len(data)}')
            return

        cmd, size, seq = struct.unpack('!3I', data[:12])
        body = data[12:]

        if cmd == CMD_LOGIN:
            self.handle_login()
        elif cmd == CMD_KEEPALIVE:
            # silent
            return
        elif cmd == CMD_PREDICT_RESULT:
            self.handle_prediction_result(body)
        else:
            self.app.log(f'[PyDealer] Unknown command: 0x{cmd:X} size={size} seq={seq}')

    def handle_login(self):
        self.logged_in = True
        self.app.log('[PyDealer] Received login => responding with CMD_LOGIN_R.')
        code = 0
        gmtype = b'BALL'  # 4 bytes field in protocol
        vid = b'B003'     # 4 bytes
        body = struct.pack('!I4s4s', code, gmtype, vid)
        packet = struct.pack('!3I', CMD_LOGIN_R, 12 + len(body), 0) + body
        self.transport.write(packet)

    def handle_prediction_result(self, body: bytes):
        # Body format: !14sh then repeated entries !2hd (group_idx, card_val, score)
        if len(body) < 16:
            self.app.log('[PyDealer] CMD_PREDICT_RESULT body too short.')
            return

        gmcode_bytes, total_cards = struct.unpack('!14sh', body[:16])
        gmcode_str = gmcode_bytes.decode('utf-8', errors='ignore').rstrip('\x00')

        entry_size = 12
        expected_size = 16 + total_cards * entry_size
        if len(body) != expected_size:
            self.app.log(f'[PyDealer] Size mismatch => expect={expected_size}, got={len(body)}')
            return

        # Parse
        offset = 16
        groups = {}
        for _ in range(total_cards):
            chunk = body[offset: offset + entry_size]
            offset += entry_size
            group_idx, val, score = struct.unpack('!2hd', chunk)
            groups.setdefault(group_idx, []).append((val, score))

        self.app.update_groups(gmcode_str, groups)

    async def connection_lost(self, exc):
        self.app.log('[PyDealer] Connection lost.')
        self.app.protocol = None
        self.logged_in = False

    # Dealer -> detector control now uses HTTP instead of socket command packets.
    # The socket connection is still kept for login + prediction result pushback.
    def send_start_predict(self):
        # Use app-generated round_id (14 bytes max on wire / BALL3 expectation)
        self.game_timestamp = self.app.current_round_id or self._new_gmcode()
        ok, detail = self.app.send_http_control('start_predict', self.game_timestamp, 2)
        if ok:
            self.app.log(f'[HTTP] Sent start_predict gmcode={self.game_timestamp}')
        else:
            self.app.log(f'[HTTP] Failed start_predict gmcode={self.game_timestamp} detail={detail}')

    def send_stop_predict(self):
        gmcode = self.game_timestamp or self.app.current_round_id or self._new_gmcode()
        ok, detail = self.app.send_http_control('stop_predict', gmcode, 0)
        if ok:
            self.app.log(f'[HTTP] Sent stop_predict gmcode={gmcode}')
        else:
            self.app.log(f'[HTTP] Failed stop_predict gmcode={gmcode} detail={detail}')


class MockDealerBall3App:
    def __init__(self, host='127.0.0.1', port=2331):
        self.host = host
        self.port = port
        self.protocol = None

        self.last_gmcode = ''
        self.groups = {}  # group_idx -> list[(val,score)]

        # Auto-dispatch / round-state
        self._date_tag = datetime.now().strftime('%y%m%d')
        self._round_seq = 0
        self.current_round_id = ''
        self._stable_last_key = None
        self._stable_count = 0
        # Number of consecutive identical predictions required before AUTO sends STOP.
        # This is configurable via the UI.
        self.stable_times = 3
        self._auto_state = 'IDLE'  # IDLE/PREDICTING/STOP_SENT

        # HTTP control path (mirrors working Postman collection)
        self.http_base_url = 'http://127.0.0.1:1234'
        self.http_method = 'POST'   # POST body matches current working Postman examples
        self.http_timeout_s = 8
        self.http_table = 'B001'
        self.http_device_id = 'obs'
        self.http_stream_id = 'OBS233jk'
        self.http_start_count = 0
        self.http_stop_count = 0
        self.http_fail_count = 0
        self.started_at = time.time()

        # GUI
        self.root = tk.Tk()
        self.root.title('Mock Dealer BALL3')
        self.root.geometry('1250x860')
        self.root.minsize(1250, 860)

        self._ui_log_file = UILogMirror(instance_timestamp_log_path(__file__, 'BALL3_UI'))
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=110, height=12)
        self.text_area.pack(padx=10, pady=10, anchor='nw')

        btn_frame = Frame(self.root)
        btn_frame.pack(pady=5, anchor='w')

        self.new_game_btn = Button(btn_frame, text='Start New Game', command=self.start_new_game)
        self.new_game_btn.grid(row=0, column=0, padx=8)

        self.start_btn = Button(btn_frame, text='Start Prediction', command=self.start_prediction)
        self.start_btn.grid(row=0, column=1, padx=8)

        self.stop_btn = Button(btn_frame, text='Stop Prediction', command=self.stop_prediction)
        self.stop_btn.grid(row=0, column=2, padx=8)

        self.auto_enabled = tk.BooleanVar(value=False)
        self.auto_btn = Button(btn_frame, text='Auto Dispatch: OFF', command=self.toggle_auto)
        self.auto_btn.grid(row=0, column=3, padx=8)

        # Stable-times control (AUTO stop threshold)
        self.stable_times_var = tk.IntVar(value=int(self.stable_times))
        Label(btn_frame, text='Stable times:').grid(row=0, column=4, padx=(16, 4))
        self.stable_spin = tk.Spinbox(
            btn_frame,
            from_=1,
            to=20,
            width=5,
            textvariable=self.stable_times_var,
            command=self._on_stable_times_changed
        )
        self.stable_spin.grid(row=0, column=5, padx=(0, 8))
        # Also react to direct typing
        self.stable_times_var.trace_add('write', lambda *_: self._on_stable_times_changed())

        # Groups display
        self.groups_frame = Frame(self.root, bd=2, relief='groove')
        self.groups_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Split: left table, right wheel
        content = Frame(self.groups_frame)
        content.pack(fill=tk.BOTH, expand=True)

        left = Frame(content)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = Frame(content, width=580)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        right.pack_propagate(False)

        self.groups_title = Label(left, text='BALL3 Results (grouped):', font=('Arial', 12, 'bold'))
        self.groups_title.pack(anchor='w', padx=8, pady=6)

        self.groups_container = Frame(left)
        self.groups_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        Label(right, text='Wheel View', font=('Arial', 12, 'bold')).pack(anchor='n')
        self.wheel = WheelCanvas(right)

        self.group_rows = {}  # group_idx -> (Label, Label)

        # logger (file + console)
        self._logger = self._setup_logger() 

        # Startup confirmation
        self.log(
            f'[INIT] HTTP control enabled => method={self.http_method}, '
            f'base={self.http_base_url}, table={self.http_table}, '
            f'deviceId={self.http_device_id}, streamId={self.http_stream_id}'
        )
        self.root.after(60_000, self._log_runtime_summary)

    def _on_stable_times_changed(self):
        """Update AUTO stop threshold from UI."""
        try:
            v = int(self.stable_times_var.get())
        except Exception:
            return
        if v < 1:
            v = 1
        if v > 20:
            v = 20
        if v != self.stable_times:
            self.stable_times = v
            self.log(f"[UI] Stable times set to {self.stable_times}")


    def _setup_logger(self) -> logging.Logger:
        """Create logs with the same folder structure as pydealerLight.

        logs/
          YYYY-MM-DD/
            YYYYMMDDHH.log

        (Hourly file name; folder per day)
        """
        base_dir = os.path.join(str(runtime_root(__file__)), 'logs')
        os.makedirs(base_dir, exist_ok=True)

        class HourlyFileHandler(logging.Handler):
            def __init__(self, root_dir: str):
                super().__init__()
                self.root_dir = root_dir
                self._cur_path = None
                self._stream = None

            def _desired_path(self) -> str:
                day = datetime.now().strftime('%Y-%m-%d')
                fn = datetime.now().strftime('%Y%m%d%H.log')
                ddir = os.path.join(self.root_dir, day)
                os.makedirs(ddir, exist_ok=True)
                return os.path.join(ddir, fn)

            def _ensure_stream(self):
                path = self._desired_path()
                if path != self._cur_path:
                    try:
                        if self._stream:
                            self._stream.close()
                    except Exception:
                        pass
                    self._cur_path = path
                    self._stream = open(path, 'a', encoding='utf-8')

            def emit(self, record):
                try:
                    self._ensure_stream()
                    msg = self.format(record)
                    self._stream.write(msg + '\n')
                    self._stream.flush()
                except Exception:
                    self.handleError(record)

            def close(self):
                try:
                    if self._stream:
                        self._stream.close()
                except Exception:
                    pass
                super().close()

        logger_ = logging.getLogger('mock_dealer_ball3')
        logger_.setLevel(logging.INFO)
        logger_.propagate = False

        if not logger_.handlers:
            fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

            fh = HourlyFileHandler(base_dir)
            fh.setFormatter(fmt)
            fh.setLevel(logging.INFO)
            logger_.addHandler(fh)

            ch = logging.StreamHandler()
            ch.setFormatter(fmt)
            ch.setLevel(logging.INFO)
            logger_.addHandler(ch)

        logger_.info('logger initialized (hourly), base_dir=%s', base_dir)
        return logger_

    def log(self, msg: str):
        # UI + logfile
        if getattr(self, '_logger', None) is not None:
            self._logger.info(msg)

        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'

        self.text_area.insert(tk.END, line + '\n')
        self.text_area.yview(tk.END)
        try:
            self._ui_log_file.write(line)
        except Exception:
            pass

    def _clear_groups_ui(self):
        for w in self.groups_container.winfo_children():
            w.destroy()
        self.group_rows.clear()

    def _build_http_payload(self, gmcode: str, gmstate: int) -> dict:
        return {
            'gmcode': str(gmcode),
            'gmstate': int(gmstate),
            'table': self.http_table,
            'deviceId': self.http_device_id,
            'streamId': self.http_stream_id,
        }

    def send_http_control(self, action: str, gmcode: str, gmstate: int):
        """Send BALL3 control over HTTP using the same content as the working Postman collection."""
        payload = self._build_http_payload(gmcode, gmstate)
        url = f"{self.http_base_url.rstrip('/')}/{action.lstrip('/')}"
        started = time.time()

        try:
            method = str(self.http_method or 'POST').upper()
            if method == 'GET':
                qs = urllib.parse.urlencode(payload)
                req = urllib.request.Request(f'{url}?{qs}', method='GET')
            else:
                raw = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=raw, method='POST')
                req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=self.http_timeout_s) as resp:
                body = resp.read().decode('utf-8', errors='ignore')
                code = getattr(resp, 'status', None) or resp.getcode()

            elapsed_ms = int((time.time() - started) * 1000)
            if action == 'start_predict':
                self.http_start_count += 1
            elif action == 'stop_predict':
                self.http_stop_count += 1

            self.log(
                f"[HTTP] {method} {url} payload={payload} => status={code}, elapsed={elapsed_ms}ms, body={body}"
            )
            return True, body

        except Exception as e:
            self.http_fail_count += 1
            elapsed_ms = int((time.time() - started) * 1000)
            return False, f'{type(e).__name__}: {e} ({elapsed_ms}ms)'

    def _log_runtime_summary(self):
        elapsed_s = int(max(0, time.time() - self.started_at))
        self.log(
            '[STATS] '
            f'uptime={elapsed_s}s, '
            f'http_start={self.http_start_count}, '
            f'http_stop={self.http_stop_count}, '
            f'http_fail={self.http_fail_count}, '
            f'auto_state={self._auto_state}'
        )
        self.root.after(60_000, self._log_runtime_summary)

    def make_round_id(self) -> str:
        """Generate 14-char round_id that fits wire format.
        Preferred: Ball3_YYMMDDNN  (NN: 2-digit sequence)
        Example:  Ball3_26022101
        """
        now = datetime.now()
        date_tag = now.strftime('%y%m%d')
        if date_tag != self._date_tag:
            self._date_tag = date_tag
            self._round_seq = 0
        self._round_seq += 1
        # 2-digit sequence to keep total length = 14
        rid = f"Ball3_{date_tag}{self._round_seq:02d}"
        return rid[:14]

    def toggle_auto(self):
        on = not self.auto_enabled.get()
        self.auto_enabled.set(on)
        self.auto_btn.configure(text=f"Auto Dispatch: {'ON' if on else 'OFF'}")
        self.log(f"[UI] Auto Dispatch => {'ON' if on else 'OFF'}")
        if on:
            self._auto_state = 'IDLE'
            # kick off if connected
            self.root.after(100, self._auto_start_round)

    def _auto_start_round(self):
        if not self.auto_enabled.get():
            return
        if not self.protocol or not getattr(self.protocol, 'logged_in', False):
            # wait for connection/login
            self.root.after(500, self._auto_start_round)
            return

        # Start a new round (reset UI + state)
        self.start_new_game()
        self.current_round_id = self.make_round_id()
        self._stable_last_key = None
        self._stable_count = 0
        self._auto_state = 'PREDICTING'
        self.log(f"[AUTO] Start round => {self.current_round_id}")
        self.protocol.send_start_predict()

    def _auto_send_stop(self):
        if not self.auto_enabled.get():
            return
        if self._auto_state != 'PREDICTING':
            return
        self._auto_state = 'STOP_SENT'
        self.log(f"[AUTO] Stable reached => send STOP for {self.current_round_id}")
        self.stop_prediction()
        # next round after a short delay (let detector flush csv)
        self.root.after(1200, self._auto_start_round)

    def _stable_key_from_groups(self, groups: dict):
        """Return canonical key tuple of 3 labels (A/J/Q/K/9/10) or None."""
        # choose best per group id, order by group id
        ranks = []
        for gid in sorted(groups.keys()):
            vals = groups.get(gid) or []
            if not vals:
                return None
            best_v, best_s = max(vals, key=lambda t: t[1])
            lab = _rank_label(best_v)
            # allow only our 6 regions
            if lab not in {'A','J','Q','K','9','10'}:
                return None
            ranks.append(lab)
        if len(ranks) != 3:
            return None
        return tuple(sorted(ranks))


    def start_new_game(self):
        self.last_gmcode = ''
        self.groups = {}
        self._clear_groups_ui()
        try:
            self.wheel.clear_balls()
        except Exception:
            pass
        self.log('[UI] Start new game => cleared UI.')

    def start_prediction(self):
        if self.protocol:
            self.protocol.send_start_predict()
        else:
            self.log('[UI] No PyDealer connection yet (wait for pydealer to connect).')

    def stop_prediction(self):
        if self.protocol:
            self.protocol.send_stop_predict()
        else:
            self.log('[UI] No PyDealer connection yet.')

    def update_groups(self, gmcode: str, groups: dict):
        self.last_gmcode = gmcode
        self.groups = groups

        # Log summary
        summary = []
        for gid in sorted(groups.keys()):
            vals = groups[gid]
            pretty = ', '.join([f'{_rank_label(v)}@{s:.2f}' for v, s in vals])
            summary.append(f'G{gid}: [{pretty}]')
        self.log(f'[PyDealer] gmcode={gmcode}, total={sum(len(v) for v in groups.values())} | ' + '  '.join(summary))

        # Update UI rows
        # Rebuild for simplicity (small data)
        self._clear_groups_ui()
        header = Frame(self.groups_container)
        header.pack(fill=tk.X, pady=2)
        Label(header, text='Group', width=10, anchor='w', font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        Label(header, text='Balls (val@score)', anchor='w', font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        for gid in sorted(groups.keys()):
            row = Frame(self.groups_container)
            row.pack(fill=tk.X, pady=2)
            Label(row, text=f'G{gid}', width=10, anchor='w').pack(side=tk.LEFT)
            vals = groups[gid]
            pretty = '   '.join([f'{_rank_label(v)}@{s:.2f}' for v, s in vals])
            Label(row, text=pretty, anchor='w').pack(side=tk.LEFT)



        # Auto-stability tracking (1Hz results expected from detector)
        try:
            key = self._stable_key_from_groups(groups)
        except Exception:
            key = None

        if key is None:
            self._stable_last_key = None
            self._stable_count = 0
        else:
            if key == self._stable_last_key:
                self._stable_count += 1
            else:
                self._stable_last_key = key
                self._stable_count = 1

            if self.auto_enabled.get() and self._auto_state == 'PREDICTING':
                self.log(f"[AUTO] stable={self._stable_count}/{self.stable_times} key={key}")
                if self._stable_count >= self.stable_times:
                    self._auto_send_stop()


        # Update wheel every time we receive a result (independent of auto mode)
        # Use best (highest score) per group as the "landed" sector
        try:
            ranks = []
            for gid in sorted(groups.keys()):
                vals = groups.get(gid) or []
                if not vals:
                    continue
                best_v, best_s = max(vals, key=lambda t: t[1])
                ranks.append(_rank_int(best_v))
            if ranks:
                self.wheel.set_balls(ranks)
        except Exception:
            # Don't crash UI if something unexpected arrives
            pass

    async def start_server(self):
        loop = asyncio.get_running_loop()
        server = await loop.create_server(lambda: MockDealerBall3Protocol(self), self.host, self.port)
        self.log(f'[PyDealer] Listening on {self.host}:{self.port}')
        async with server:
            await server.serve_forever()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self.start_server())

        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)
        self.poll_loop(self.loop)
        self.root.mainloop()

    def poll_loop(self, loop):
        loop.call_soon(self.root.after, 100, self.poll_loop, loop)
        loop.run_until_complete(asyncio.sleep(0))

    def on_closing(self):
        try:
            self.root.quit()
            self.root.destroy()
        finally:
            # best-effort stop loop
            try:
                self.loop.stop()
            except Exception:
                pass


def main():
    app = MockDealerBall3App('127.0.0.1', 2331)
    app.run()


if __name__ == '__main__':
    main()