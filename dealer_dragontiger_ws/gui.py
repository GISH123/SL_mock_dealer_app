import time
import logging
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from pathlib import Path
import json  # <-- added

log = logging.getLogger("GUI")

CARDS_DIR = Path(__file__).resolve().parent.parent / "card_shown_ui" / "greywyvern-cardset"
# ---- Sidecar persistence for gaps + order (never writes to .env) ----
PERSIST_PATH = Path(__file__).resolve().parent / "last_save_default_gap_value.env"
def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def _load_saved_from_dotenv_key():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return None
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if s and not s.startswith("#") and s.startswith("last_save_default_gap_value="):
                return json.loads(s.split("=", 1)[1].strip())
    except Exception:
        return None
    return None

CARD_W, CARD_H = 80, 120

class DealerGUI:
    def __init__(
        self,
        root: tk.Tk,
        *,
        on_start_pred,
        on_stop_pred,
        on_dispatch_idx=None,
        on_toggle_dvr=None,
        on_mode_selected=None,
        on_save_result=None,
        max_slots: int = 6,
    ):
        # external callbacks
        self.on_start_pred    = on_start_pred
        self.on_stop_pred     = on_stop_pred
        self.on_dispatch_idx  = on_dispatch_idx
        self.on_toggle_dvr    = on_toggle_dvr
        self.on_mode_selected = on_mode_selected
        self.on_save_result   = on_save_result

        # dispatch schedule config
        self.max_slots = int(max_slots)
        self._base_order = [1, 3, 2, 4, 5, 6]
        self.dispatch_all_seq = self._base_order[: self.max_slots]
        self.dispatch_all_interval_var = tk.StringVar(value="0.5")   # seconds between indices
        self.save_gap_var              = tk.StringVar(value="9.9")   # seconds after last dispatch -> Save
        self.stop_gap_var              = tk.StringVar(value="10.0")  # seconds after last dispatch -> Stop
        self.dispatch_all_gap_var      = tk.StringVar(value="5.0")   # seconds between rounds

        # state flags
        self._auto_loop         = False
        self._round_running     = False
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self._round_no          = 0
        self._last_dispatch_ts  = None  # wallclock seconds of last dispatch
        self._manual_stop_after = None  # tk after handle for delayed manual stop

        # DT auto state
        self._dt_active = False
        self._dt_step = 0
        self._dt_waiting_for = None
        self._dt_timeout_after = None
        self._detected_flags = {i: False for i in [1,2,3,4,5,6]}

        self.root = root
        root.title("Dragon-Tiger Dealer")

        # Status
        self.status_label = tk.Label(
            root, text="Waiting to be connected to Detector...",
            fg="red", font=("Arial", 12, "bold")
        )
        self.status_label.pack()
        log.info("UI: Waiting to be connected to Detector...")

        # GM base
        gmf = tk.Frame(root); gmf.pack(pady=(0, 4))
        tk.Label(gmf, text="GMCode base:").pack(side=tk.LEFT)
        self.gmcode_var = tk.StringVar(value="")
        self.gm_entry = tk.Entry(gmf, textvariable=self.gmcode_var, width=22)
        self.gm_entry.pack(side=tk.LEFT, padx=4)

        # Mode selector
        mode_frame = tk.Frame(root); mode_frame.pack(pady=(0, 6))
        tk.Label(mode_frame, text="Detector mode (Please click one mode):").pack(side=tk.LEFT)

        self.mode_var = tk.StringVar(value="")   # start with nothing selected
        self._mode_radios = []
        for txt, val in (("TCP", "tcp"), ("WS", "ws"), ("Both", "both")):
            rb = tk.Radiobutton(
                mode_frame, text=txt, value=val, variable=self.mode_var,
                command=(on_mode_selected if on_mode_selected else (lambda: None)),
                indicatoron=0, relief="raised", highlightthickness=0, bd=1, padx=6, pady=2,
            )
            rb.pack(side=tk.LEFT, padx=3)
            self._mode_radios.append(rb)

        # DVR toggle
        self.dvr_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mode_frame, text="DVR", variable=self.dvr_var,
            command=(lambda: on_toggle_dvr(bool(self.dvr_var.get())) if on_toggle_dvr else None),
        ).pack(side=tk.LEFT, padx=(12, 0))

        # Controls
        btns = tk.Frame(root); btns.pack(pady=4)
        self.btn_start = tk.Button(btns, text="(+) Start New Round && Prediction", command=on_start_pred)
        self.btn_start.pack(side=tk.LEFT, padx=4)

        # NOTE: wrap Stop so we can enforce a stop-gap even on manual click
        self.btn_stop_prediction = tk.Button(btns, text="Stop Prediction", command=self._on_stop_clicked)
        self.btn_stop_prediction.pack(side=tk.LEFT, padx=4)

        self.btn_save = tk.Button(btns, text="Save Result", command=on_save_result)
        self.btn_save.pack(side=tk.LEFT, padx=4)
        self.disable_save_result()  # enabled only after first AB0004

        # Dispatch per index
        self.idx_frame = tk.Frame(root); self.idx_frame.pack(pady=(0, 4))
        self.disable_start_prediction()
        self.disable_stop_prediction()
        self.disable_dispatch_buttons()

        ORDER = self._base_order[: self.max_slots]
        self.dispatch_buttons = []
        for col, idx in enumerate(ORDER):
            b = tk.Button(self.idx_frame, text=f"Dispatch {idx}",
                          command=lambda k=idx: self._dispatch_idx(k),
                          state="disabled")
            b.grid(row=0, column=col, padx=2)
            self.dispatch_buttons.append(b)

        # Card slots
        cards = tk.Frame(root); cards.pack(pady=4)
        self.labels, self._cache = [], {}
        self.status_labels = []
        # empty = no card
        try:
            _empty_img = Image.new('RGBA', (CARD_W, CARD_H), (255, 255, 255, 0))
            self._cache['_EMPTY'] = ImageTk.PhotoImage(_empty_img)
        except Exception:
            self._cache['_EMPTY'] = None
        # cardback image (RED) for classid==0
        try:
            _cb_path = CARDS_DIR / 'backa.png'
            _cb_img = Image.open(_cb_path).resize((CARD_W, CARD_H), Image.LANCZOS)
            self._cache['_CARDBACK'] = ImageTk.PhotoImage(_cb_img)
        except Exception:
            self._cache['_CARDBACK'] = None

        for i in range(self.max_slots):
            lbl = tk.Label(cards, image=self._cache.get('_EMPTY'), relief='solid', bd=1)
            lbl.image = self._cache.get('_EMPTY')
            lbl.grid(row=0, column=i, padx=2, pady=2)
            self.labels.append(lbl)
            sl = tk.Label(cards, text='empty', fg='gray25', font=('Arial', 9))
            sl.grid(row=1, column=i, padx=2, pady=(0,2))
            self.status_labels.append(sl)


        # Track whether cardback was ever seen for each slot (for status text)
        self._cardback_seen = [False for _ in range(self.max_slots)]

        # Dispatch All controls (float-friendly Spinboxes)
        all_frame = tk.Frame(root); all_frame.pack(pady=(6, 2))
        def _spin(parent, var, w=5, frm=0.0, to=999.0, inc=0.1):
            try:
                sb = tk.Spinbox(parent, textvariable=var, from_=frm, to=to, increment=inc,
                                width=w, justify="center")
            except Exception:
                sb = tk.Entry(parent, textvariable=var, width=w, justify="center")
            return sb

        tk.Label(all_frame, text="Dispatch All every (s):").pack(side=tk.LEFT)
        _spin(all_frame, self.dispatch_all_interval_var).pack(side=tk.LEFT, padx=(6, 12))

        tk.Label(all_frame, text="Save gap (s):").pack(side=tk.LEFT)
        _spin(all_frame, self.save_gap_var).pack(side=tk.LEFT, padx=(6, 12))

        tk.Label(all_frame, text="Stop gap (s):").pack(side=tk.LEFT)
        _spin(all_frame, self.stop_gap_var).pack(side=tk.LEFT, padx=(6, 12))

        tk.Label(all_frame, text="Gap (s):").pack(side=tk.LEFT)
        _spin(all_frame, self.dispatch_all_gap_var).pack(side=tk.LEFT, padx=(6, 12))

        self.btn_dispatch_all = tk.Button(all_frame, text="Dispatch All", command=self.on_dispatch_all)
        self.btn_dispatch_all.pack(side=tk.LEFT)

        # ===== DT Auto row (separate from Dispatch All) =====
        # NOTE:
        #   - DT Auto was designed for DT (3 cards).
        #   - In Latency mode (max_slots=1), older builds could still dispatch 3 indices (e.g. 1,3,2)
        #     and then hang forever because idx 3/2 are not visible in the UI, so "detected" events
        #     never fire for them.
        #   - We clamp DT Auto to min(max_slots, 3) cards in _dt_start_round().
        #   - For BAC (max_slots=6), prefer using "Dispatch All" instead.
        dt_frame = tk.Frame(root); dt_frame.pack(pady=(2, 6))
        self.btn_auto_dt = tk.Button(dt_frame, text="DT_Auto Dispatch When Detected", command=self._toggle_auto_dt)
        self.btn_auto_dt.pack(side=tk.LEFT, padx=(0,10))
        tk.Label(dt_frame, text="Order:").pack(side=tk.LEFT, padx=(0,4))
        self.order_vars = []
        for _v in ["1","3","2","4","5","6"]:
            v = tk.StringVar(value=_v)
            self.order_vars.append(v)
            tk.Entry(dt_frame, textvariable=v, width=2, justify="center").pack(side=tk.LEFT, padx=1)

        # Timeline hint
        self.timeline = tk.Label(root, text="", fg="gray25", font=("Arial", 9))
        self.timeline.pack(pady=(2, 6))

        # Load persisted gaps & order
        self._load_and_apply_saved()

        # Dispatch-All Auto round state (event-driven end-of-round)
        self._auto_round_running = False
        self._auto_round_id = 0
        self._auto_expected_idxs = []   # indices that must be VALUE-detected for the round to finish
        self._auto_detected = {}        # idx -> bool (VALUE-detected)
        self._auto_all_dispatched_ts = None
        self._auto_last_value_ts = None
        self._auto_end_after_save = None
        self._auto_end_after_stop = None
        self._auto_end_after_next = None


        # Hotkeys
        root.bind("<+>",        lambda _e: self.btn_start.invoke())
        root.bind("<=>",        lambda _e: self.btn_start.invoke())
        root.bind("<KP_Add>",   lambda _e: self.btn_start.invoke())
        root.bind("<Return>",   lambda _e: self.btn_stop_prediction.invoke())

    # --------------- helpers / state ---------------
    def lock_mode_selector(self):
        for rb in self._mode_radios: rb.config(state="disabled")

    def set_status(self, txt: str, color: str = "Black"):
        # mirror UI text to log
        log.info("UI: %s", txt)
        self.status_label.config(text=txt, fg=color)
        self.root.update_idletasks()

    def _set_timeline(self, txt: str):
        self.timeline.config(text=txt)
        if txt:
            log.info("UI timeline: %s", txt)

    def on_connected(self):
        self.set_status("Connected", "green")
        self.btn_start.config(state="normal")

    # Round UI flips
    def on_round_started(self):
        self.btn_start.config(state="normal")
        self.btn_stop_prediction.config(state="normal")
        for b in self.dispatch_buttons: b.config(state="normal")
        self.disable_dispatch_all()
        self._round_running = True
        self._ready_to_dispatch = False
        self._last_dispatch_ts = None

    def on_prediction_started(self):
        self._round_no += 1
        self._first_result_seen = False
        self.btn_start.config(state="disabled")
        self.btn_stop_prediction.config(state="normal")
        self._ready_to_dispatch = True
        self._last_dispatch_ts = None

        # reset slot UI state for a new round
        try:
            self._cardback_seen = [False for _ in range(self.max_slots)]
            empty_img = self._cache.get('_EMPTY')
            for i in range(len(self.labels)):
                if empty_img is not None:
                    self.labels[i].config(image=empty_img)
                    self.labels[i].image = empty_img
            if hasattr(self, 'status_labels'):
                for sl in self.status_labels:
                    sl.config(text='empty')
        except Exception:
            pass


    def on_first_result(self):
        if not self._first_result_seen:
            self._first_result_seen = True
            self.enable_save_result()

    def on_prediction_stopped(self):
        self.btn_stop_prediction.config(state="disabled")
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self.disable_save_result()
        self._last_dispatch_ts = None
        self._set_timeline("")

    def on_round_ended(self):
        self.btn_start.config(state="disabled")
        self.btn_stop_prediction.config(state="disabled")
        for b in self.dispatch_buttons: b.config(state="disabled")
        self.enable_dispatch_all()
        self._round_running = False
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self.disable_save_result()
        self._last_dispatch_ts = None
        self._set_timeline("")

    # GM helpers
    def set_gm_base(self, base: str) -> None: self.gmcode_var.set(base)
    def get_gm_base(self) -> str: return self.gmcode_var.get().strip()

    # Enable/disable helpers
    def disable_start_prediction(self): self.btn_start.config(state="disabled")
    def enable_start_prediction(self):  self.btn_start.config(state="normal")
    def enable_stop_prediction(self):   self.btn_stop_prediction.config(state="normal")
    def disable_stop_prediction(self):  self.btn_stop_prediction.config(state="disabled")
    def enable_dispatch_buttons(self):  [c.config(state="normal") for c in self.idx_frame.winfo_children()]
    def disable_dispatch_buttons(self): [c.config(state="disabled") for c in self.idx_frame.winfo_children()]
    def enable_dispatch_all(self):      self.btn_dispatch_all.config(state="normal")
    def disable_dispatch_all(self):     self.btn_dispatch_all.config(state="disabled")
    def enable_save_result(self):       self.btn_save.config(state="normal")
    def disable_save_result(self):      self.btn_save.config(state="disabled")

    # ---- parsing helpers
    def _get_float(self, var: tk.StringVar, default: float, *, clamp_min=None, clamp_max=None) -> float:
        s = (var.get() or "").strip().replace(",", ".")
        try:
            v = float(s)
        except Exception:
            v = default
            var.set(str(default))
        if clamp_min is not None and v < clamp_min: v = clamp_min
        if clamp_max is not None and v > clamp_max: v = clamp_max
        return v

    # Card painting

    def _get_dispatch_seq(self):
        """Return dispatch index sequence for current mode (filtered by active indices)."""
        active = list(getattr(self, "dispatch_all_seq", []))[: self.max_slots]
        active_set = set(active)

        seq = []
        for v in getattr(self, "order_vars", []):
            try:
                i = int(str(v.get()).strip())
            except Exception:
                continue
            if i in active_set and i not in seq:
                seq.append(i)

        # append missing active indices in the base order for this mode
        for i in active:
            if i not in seq:
                seq.append(i)

        return seq

    def update_card(self, idx: int, card_val: int) -> None:
        """Update UI for a predicted result.

        Rules:
        - cardback (classid==0) is shown using backa.png, but is NOT counted as 'card detected'.
        - only value/suit (classid!=0) counts toward Dispatch-All round completion.
        """
        ORDER_MAP = {1:0, 3:1, 2:2, 4:3, 5:4, 6:5}
        slot = ORDER_MAP.get(int(idx))
        if slot is None or slot >= len(self.labels):
            return

        # ---- cardback ----
        if int(card_val) == 0:
            cb = self._cache.get('_CARDBACK')
            if cb is not None:
                self.labels[slot].config(image=cb)
                self.labels[slot].image = cb
            self._cardback_seen[slot] = True
            if hasattr(self, 'status_labels') and slot < len(self.status_labels):
                self.status_labels[slot].config(text='cardback')
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            return

        # ---- Normal value/suit painting ----
        if   0  <= card_val <= 15: suit = "C"
        elif 16 <= card_val <= 31: suit = "D"
        elif 32 <= card_val <= 47: suit = "S"
        elif 48 <= card_val <= 63: suit = "H"
        else: 
            return

        rank_num = int(card_val) % 16
        if not (1 <= rank_num <= 13):
            return

        key = f"{suit}{rank_num:02d}"
        if key not in self._cache:
            try:
                img_path = CARDS_DIR / f"{key}.png"
                pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
                self._cache[key] = ImageTk.PhotoImage(pil_img)
            except Exception:
                return

        self.labels[slot].config(image=self._cache[key])
        self.labels[slot].image = self._cache[key]

        # status label: show whether cardback was seen, and the current class key
        if hasattr(self, 'status_labels') and slot < len(self.status_labels):
            prefix = "cb " if (hasattr(self, '_cardback_seen') and slot < len(self._cardback_seen) and self._cardback_seen[slot]) else ""
            self.status_labels[slot].config(text=f"{prefix}{key}")

        try:
            self.root.update_idletasks()
        except Exception:
            pass

        # Mark as VALUE-detected for auto features
        try:
            self.note_value_detected(idx)
        except Exception:
            pass



    def update_latency_state(self, idx: int, state: str) -> None:
        """Latency UI helper.

        state in {'cardback','card','empty'}
        - cardback: show back image, does NOT count as complete
        - empty: show empty image, does NOT count as complete
        - card: show a neutral placeholder and allow completion via note_value_detected()
        """
        ORDER_MAP = {1:0, 3:1, 2:2, 4:3, 5:4, 6:5}
        slot = ORDER_MAP.get(int(idx))
        if slot is None or slot >= len(self.labels):
            return

        state = (state or '').lower().strip()
        if state == 'cardback':
            cb = self._cache.get('_CARDBACK')
            if cb is not None:
                self.labels[slot].config(image=cb)
                self.labels[slot].image = cb
            try:
                self._cardback_seen[slot] = True
            except Exception:
                pass
            if hasattr(self, 'status_labels') and slot < len(self.status_labels):
                self.status_labels[slot].config(text='cardback')

        elif state == 'empty':
            self.empty_card(slot)
            if hasattr(self, 'status_labels') and slot < len(self.status_labels):
                self.status_labels[slot].config(text='empty')

        elif state == 'card':
            # Do NOT pretend it's a real 64-class card id (avoid A01 confusion)
            ph = self._cache.get('_EMPTY')
            if ph is not None:
                self.labels[slot].config(image=ph)
                self.labels[slot].image = ph
            if hasattr(self, 'status_labels') and slot < len(self.status_labels):
                self.status_labels[slot].config(text='card')

        try:
            self.root.update_idletasks()
        except Exception:
            pass


    def note_value_detected(self, idx: int) -> None:
        """Mark idx as VALUE-detected (used by Dispatch-All auto end and DT-auto progression)."""
        # ---- Dispatch-All Auto round logic ----
        try:
            if getattr(self, '_auto_loop', False) and getattr(self, '_auto_round_running', False):
                exp = list(getattr(self, '_auto_expected_idxs', []))
                if int(idx) in exp:
                    if not self._auto_detected.get(int(idx), False):
                        self._auto_detected[int(idx)] = True
                        if not hasattr(self, '_auto_detected_ts'):
                            self._auto_detected_ts = {}
                        self._auto_detected_ts[int(idx)] = time.time()
                    self._maybe_arm_auto_round_end()
        except Exception:
            pass

        # ---- DT Auto event-driven ----
        try:
            if self._dt_active and self._dt_waiting_for == int(idx):
                self._detected_flags[int(idx)] = True
                try:
                    print('[DT-EVT] detected', idx)
                except Exception:
                    pass
                self._dt_step += 1
                self._dt_waiting_for = None
                if self._dt_timeout_after:
                    try:
                        self.root.after_cancel(self._dt_timeout_after)
                    except Exception:
                        pass
                    self._dt_timeout_after = None
                self.root.after(1, self._dt_dispatch_next)
        except Exception:
            pass
    def _load_and_apply_saved(self):
        vals = None
        if PERSIST_PATH.exists():
            try: vals = _load_json(PERSIST_PATH)
            except Exception: vals = None
        if vals is None:
            vals = _load_saved_from_dotenv_key()
        if isinstance(vals, dict):
            def _set(var, key, dflt=None):
                if key in vals:
                    try: var.set(str(vals[key]))
                    except Exception: pass
                elif dflt is not None:
                    try: var.set(str(dflt))
                    except Exception: pass
            _set(self.dispatch_all_interval_var, "DISPATCH_ALL_EVERY", "0.5")
            _set(self.save_gap_var,              "SAVE_GAP",            "9.9")
            _set(self.stop_gap_var,              "STOP_GAP",            "10.0")
            _set(self.dispatch_all_gap_var,      "ROUND_GAP",           "5.0")
            try:
                for i,n in enumerate(vals.get("ORDER", [1,3,2,4,5,6])[:6]):
                    self.order_vars[i].set(str(int(n)))
            except Exception:
                pass

    def _save_from_ui(self):
        vals = {}
        def _get(var, key, dflt):
            try: vals[key] = float(var.get())
            except Exception: vals[key] = float(dflt)
        _get(self.dispatch_all_interval_var, "DISPATCH_ALL_EVERY", 0.5)
        _get(self.save_gap_var,              "SAVE_GAP",            9.9)
        _get(self.stop_gap_var,              "STOP_GAP",            10.0)
        _get(self.dispatch_all_gap_var,      "ROUND_GAP",           5.0)
        try:
            vals["ORDER"] = [int(v.get() or "0") for v in self.order_vars][:6]
        except Exception:
            vals["ORDER"] = [1,3,2,4,5,6]
        try:
            PERSIST_PATH.write_text(json.dumps(vals), encoding="utf-8")
        except Exception:
            pass

    def empty_card(self, slot: int) -> None:
        """Reset a slot to empty (no card)."""
        try:
            img = self._cache.get('_EMPTY')
            if img is not None and slot < len(self.labels):
                self.labels[slot].config(image=img)
                self.labels[slot].image = img
            if hasattr(self, 'status_labels') and slot < len(self.status_labels):
                self.status_labels[slot].config(text='')
        except Exception:
            pass
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _toggle_auto_dt(self):
        # DT Auto is meant for <=3 slots (Latency=1, DT=3). For BAC (6), use Dispatch All.
        want_enable = not self._dt_active
        if want_enable and int(getattr(self, "max_slots", 6)) > 3:
            self.set_status("DT Auto is for Latency/DT only. Use 'Dispatch All' for BAC.", "orange")
            return

        self._dt_active = want_enable
        try:
            self.btn_auto_dt.config(text=("Stop Auto Dispatch New Round" if self._dt_active else "DT_Auto Dispatch When Detected"))
        except Exception:
            pass
        if self._dt_active:
            self._dt_start_round()
        else:
            try:
                if self._dt_timeout_after:
                    self.root.after_cancel(self._dt_timeout_after)
                    self._dt_timeout_after = None
            except Exception:
                pass
            self._set_timeline("")

    def _dt_start_round(self):
        if not self._dt_active: return
        # Parse order from UI; clamp to min(max_slots, 3) so Latency won't dispatch extra indices.
        try:
            order = []
            for v in getattr(self, "order_vars", []):
                s = v.get().strip()
                if not s: continue
                n = int(s)
                if 1 <= n <= 6 and n not in order:
                    order.append(n)
        except Exception:
            order = [1,3,2,4,5,6]

        need = min(int(getattr(self, "max_slots", 3)), 3)
        need = max(1, need)
        self._dt_order3 = (order or [1,3,2])[:need]
        self._dt_step = 0
        self._dt_waiting_for = None
        if callable(self.on_start_pred): self.on_start_pred()
        self._dt_wait_ready(0)

    def _dt_wait_ready(self, tries):
        if not self._dt_active: return
        if self._ready_to_dispatch:
            self._dt_dispatch_next()
            return
        if tries >= 100:
            self.set_status("DT Auto: timeout waiting for ready", "red")
            self._toggle_auto_dt()
            return
        self.root.after(100, lambda: self._dt_wait_ready(tries+1))

    def _dt_dispatch_next(self):
        if not self._dt_active:
            return

        # If we've already dispatched & detected all 3, save -> stop -> wait gap -> next round
        if self._dt_step >= len(getattr(self, "_dt_order3", [])):
            if callable(self.on_save_result):
                self.on_save_result()
            # small guard delay so result can propagate
            self.root.after(200, (lambda: self.on_stop_pred() if callable(self.on_stop_pred) else None))
            gap = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)
            self.root.after(int(max(0.0, gap) * 1000),
                            self._dt_start_round if self._dt_active else (lambda: None))
            return

        # Otherwise dispatch the next index and WAIT for its detection (no timeout)
        idx = int(self._dt_order3[self._dt_step])
        self._dt_waiting_for = idx

        # clear any stale flag
        try:
            self._detected_flags[idx] = False
        except Exception:
            pass

        # Always send the packet (even if _ready_to_dispatch flips a bit late)
        if callable(self.on_dispatch_idx):
            self.on_dispatch_idx(idx)
        self._last_dispatch_ts = time.time()

        try:
            print("[DT-EVT] dispatch", idx)
        except Exception:
            pass

        # IMPORTANT: do NOT schedule any stop-gap timeout here.
        # We only advance/finish when update_card(idx, ...) fires.
        # If something gets stuck, the user can stop via the toggle button.
        # Also cancel any previously armed timeout from an older build.
        try:
            if self._dt_timeout_after:
                self.root.after_cancel(self._dt_timeout_after)
                self._dt_timeout_after = None
        except Exception:
            pass

    def _dt_on_timeout(self):
        try: print("[DT-EVT] timeout on idx", self._dt_waiting_for)
        except Exception: pass
        if callable(self.on_save_result): self.on_save_result()
        self.root.after(200, (lambda: self.on_stop_pred() if callable(self.on_stop_pred) else None))
        gap = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)
        self.root.after(int(max(0.0, gap)*1000), self._dt_start_round if self._dt_active else (lambda: None))

    # -------- Dispatch (and timing) --------
    def _dispatch_idx(self, idx: int):
        if not self._ready_to_dispatch:
            print(f"[GUI] skip dispatch idx={idx} (round not ready)")
            return
        if callable(self.on_dispatch_idx):
            self.on_dispatch_idx(idx)
        self._last_dispatch_ts = time.time()

    def _dispatch_idx_force(self, idx: int):
        """Always send the packet (used by DT auto)."""
        if callable(self.on_dispatch_idx):
            self.on_dispatch_idx(idx)
        self._last_dispatch_ts = time.time()

    def _on_stop_clicked(self):
        """Manual Stop button → enforce stop-gap from last dispatch."""
        stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)
        now = time.time()
        if self._last_dispatch_ts is not None:
            elapsed = now - self._last_dispatch_ts
            delay = max(0.0, stop_gap - elapsed)
        else:
            delay = 0.0

        if delay <= 0:
            if callable(self.on_stop_pred): self.on_stop_pred()
            try: self._save_from_ui()
            except Exception: pass
            return

        # schedule delayed stop, debounce clicks
        if self._manual_stop_after:
            try: self.root.after_cancel(self._manual_stop_after)
            except Exception: pass
        self.disable_stop_prediction()
        self.set_status(f"Stop scheduled in {delay:.1f}s (respecting stop gap)…", color="blue")
        self._manual_stop_after = self.root.after(int(delay * 1000), self._fire_manual_stop)

    def _fire_manual_stop(self):
        self._manual_stop_after = None
        if callable(self.on_stop_pred): self.on_stop_pred()
        try: self._save_from_ui()          # ensure gaps persist on delayed stop
        except Exception: pass


    # -----------------------
    # Dispatch-All end-of-round scheduler (event-driven)
    # -----------------------
    def _auto_cancel_round_end(self):
        """Cancel any pending Save/Stop/Next callbacks for Dispatch-All auto."""
        for attr in ("_auto_end_after_save", "_auto_end_after_stop", "_auto_end_after_next"):
            h = getattr(self, attr, None)
            if h:
                try:
                    self.root.after_cancel(h)
                except Exception:
                    pass
            setattr(self, attr, None)
        self._auto_round_end_armed = False

    def _maybe_arm_auto_round_end(self):
        """Arm Save/Stop/Next only after ALL expected indices have VALUE detections (cardback ignored)."""
        if not getattr(self, "_auto_loop", False):
            return
        if not getattr(self, "_auto_round_running", False):
            return

        exp = list(getattr(self, "_auto_expected_idxs", []))
        if not exp:
            return

        # Must have finished dispatching all indices (Option A)
        all_dispatched_ts = getattr(self, "_auto_all_dispatched_ts", None)
        if all_dispatched_ts is None:
            return

        detected = getattr(self, "_auto_detected", {})
        if not all(detected.get(int(i), False) for i in exp):
            return

        ts_map = getattr(self, "_auto_detected_ts", {})
        ts_vals = [ts_map.get(int(i)) for i in exp]
        if any(t is None for t in ts_vals):
            return

        last_val_ts = max(ts_vals) if ts_vals else all_dispatched_ts
        anchor = max(all_dispatched_ts, last_val_ts)

        save_gap = self._get_float(self.save_gap_var, 2.0, clamp_min=0.0)
        stop_gap = self._get_float(self.stop_gap_var, 5.0, clamp_min=0.0)
        round_gap = self._get_float(self.dispatch_all_gap_var, 15.0, clamp_min=0.0)

        rid = int(getattr(self, "_auto_round_id", 0))

        def _still_current_round() -> bool:
            return (
                getattr(self, "_auto_loop", False)
                and int(getattr(self, "_auto_round_id", 0)) == rid
            )

        def _do_save():
            if not _still_current_round():
                return
            try:
                self._save_from_ui()
            except Exception:
                pass
            if callable(self.on_save_result):
                self.on_save_result()

        def _do_stop():
            if not _still_current_round():
                return
            try:
                self._save_from_ui()
            except Exception:
                pass
            if callable(self.on_stop_pred):
                self.on_stop_pred()

        def _do_next():
            if not _still_current_round():
                return
            # clear per-round state and kickoff the next round
            self._auto_round_running = False
            self._auto_round_end_armed = False
            self._kickoff_round()

        now = time.time()
        d_save = max(0.0, (anchor + save_gap) - now)
        d_stop = max(0.0, (anchor + save_gap + stop_gap) - now)
        d_next = max(0.0, (anchor + save_gap + stop_gap + round_gap) - now)

        # (re)arm schedule
        self._auto_cancel_round_end()
        self._auto_round_end_armed = True
        self._auto_end_after_save = self.root.after(int(d_save * 1000), _do_save)
        self._auto_end_after_stop = self.root.after(int(d_stop * 1000), _do_stop)
        self._auto_end_after_next = self.root.after(int(d_next * 1000), _do_next)

        self._set_timeline(
            f"Save@+{save_gap:.1f}s | Stop@+{save_gap + stop_gap:.1f}s | Next@+{save_gap + stop_gap + round_gap:.1f}s"
        )

    def on_dispatch_all(self):
        if getattr(self, "_round_running", False):
            return
        self._auto_loop = not getattr(self, "_auto_loop", False)
        self.btn_dispatch_all.config(text="Stop Dispatch All" if self._auto_loop else "Dispatch All")
        if self._auto_loop:
            self._kickoff_round()
        else:
            # stop auto → cancel any pending Save/Stop/Next
            try:
                self._auto_round_running = False
                self._auto_cancel_round_end()
            except Exception:
                pass
            self._set_timeline("")

    def _kickoff_round(self):
        if not self._auto_loop: return
        if callable(self.on_start_pred): self.on_start_pred()
        self._wait_and_schedule()

    def _deferred_save(self, max_wait_ms=3000, tick_ms=150):
        """Wait until first result is seen (or timeout) before saving."""
        waited = {"ms": 0}
        def _step():
            if self._first_result_seen or waited["ms"] >= max_wait_ms:
                if callable(self.on_save_result): self.on_save_result()
                return
            waited["ms"] += tick_ms
            self.root.after(tick_ms, _step)
        _step()

    def _wait_and_schedule(self, tries: int = 0) -> None:
        if not self._auto_loop:
            return

        if self._ready_to_dispatch:
            interval = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
            delay_ms = max(50, int(interval * 1000))

            # start a new auto round
            self._auto_round_id = int(getattr(self, "_auto_round_id", 0)) + 1
            rid = self._auto_round_id
            self._auto_round_running = True
            self.dispatch_all_seq = self._get_dispatch_seq()[: getattr(self, "max_slots", 6)]
            self._auto_expected_idxs = list(self.dispatch_all_seq)
            self._auto_detected = {int(i): False for i in self._auto_expected_idxs}
            self._auto_all_dispatched_ts = None
            self._auto_detected_ts = {int(i): None for i in self._auto_expected_idxs}
            self._auto_round_end_armed = False
            self._auto_cancel_round_end()

            total = len(self.dispatch_all_seq)

            def _dispatch_and_mark(i, is_last=False):
                if not self._auto_loop:
                    return
                if int(getattr(self, "_auto_round_id", 0)) != rid:
                    return
                self._dispatch_idx(i)
                if is_last:
                    self._auto_all_dispatched_ts = time.time()
                    # if values arrived early, we may be ready now
                    self._maybe_arm_auto_round_end()

            for step, idx in enumerate(self.dispatch_all_seq):
                is_last = (step == total - 1)
                self.root.after(step * delay_ms, lambda i=idx, last=is_last: _dispatch_and_mark(i, last))

            ts = f"Dispatch@0,{interval:.1f},{2*interval:.1f}" + ("…" if len(self.dispatch_all_seq) > 3 else "")
            self._set_timeline(f"{ts} | waiting VALUE detections…")
            return

        # Retry ~5s waiting for start-prediction confirmation
        if tries >= 50:
            print("[GUI] start-prediction not confirmed, stopping Dispatch All")
            self._auto_loop = False
            self._auto_round_running = False
            try:
                self._auto_cancel_round_end()
            except Exception:
                pass
            self.btn_dispatch_all.config(text="Dispatch All")
            self.enable_dispatch_all()
            self._set_timeline("")
            return

        self.root.after(100, lambda: self._wait_and_schedule(tries + 1))

