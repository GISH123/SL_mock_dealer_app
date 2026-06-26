import time
import logging
import re
import sys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from pathlib import Path
import json  # <-- added
from datetime import datetime
from tkinter.scrolledtext import ScrolledText

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_runtime import UILogMirror, instance_timestamp_log_path, resolve_card_pack_dir, resolve_sidecar_path

log = logging.getLogger("GUI")


class TkTextLogHandler(logging.Handler):
    """Route python logging output into DealerGUI's scrollable UI log box.

    Must NOT call logging inside emit(), otherwise it can recurse.
    """

    def __init__(self, gui, level=logging.INFO):
        super().__init__(level)
        self.gui = gui
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    def emit(self, record):
        try:
            msg = self.format(record)

            # Annotate DT command codes in logs (so cmd=0xBA0007 is readable)
            try:
                # example text: cmd=0xBA00007 or cmd=0xBA0007
                m = re.search(r"cmd=0x([0-9A-Fa-f]+)", msg)
                if m and "CMD_" not in msg:
                    code = int(m.group(1), 16)
                    name_map = {
                        0xBA0002: "CMD_LOGIN_R_D2C",
                        0xBA0003: "CMD_START_PREDICT_D2C",
                        0xBA0004: "CMD_STOP_PREDICT_D2C",
                        0xBA0006: "CMD_DISPATCH_IDX_D2C",
                        0xBA0007: "CMD_SAVE_RESULT_D2C",
                        0xBA0008: "CMD_CANCEL_RESULT_D2C",
                        0xAB0001: "CMD_KEEPALIVE",
                        0xAB0002: "CMD_LOGIN",
                        0xAB0004: "CMD_PREDICT_RESULT",
                    }
                    nm = name_map.get(code)
                    if nm:
                        msg = f"{msg}  ({nm})"
            except Exception:
                pass

            self.gui._append_ui_log(msg)
        except Exception:

            # never crash the app due to logging UI
            pass

CARDS_DIR = resolve_card_pack_dir(__file__)
# ---- Sidecar persistence for gaps + order (never writes to .env) ----
PERSIST_PATH = resolve_sidecar_path(__file__, "last_save_default_gap_value.env")
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
    def _save_result_log_text(self, kind: str, save_gap: float | None = None, waited_ms=None, first_result_seen=None) -> str:
        mode = (self.mode_var.get() or '').strip().lower()
        gap_part = f" (Save gap={save_gap:.2f}s)" if save_gap is not None else ''
        if kind == 'scheduled':
            if mode == 'http':
                return f"[SEND] SaveResult now (scheduled) via HTTP /save_result{gap_part}"
            if mode == 'both':
                return f"[SEND] SaveResult now (scheduled) via TCP+HTTP (cmd=0xBA0007 + HTTP /save_result){gap_part}"
            return f"[SEND] SaveResult now (scheduled) (cmd=0xBA0007){gap_part}"
        if kind == 'manual':
            if mode == 'http':
                return "[SEND] SaveResult (manual) via HTTP /save_result"
            if mode == 'both':
                return "[SEND] SaveResult (manual) via TCP+HTTP (cmd=0xBA0007 + HTTP /save_result)"
            return "[SEND] SaveResult (manual) (cmd=0xBA0007)"
        if kind == 'deferred':
            tail = f" (waited_ms={waited_ms} first_result={first_result_seen})"
            if mode == 'http':
                return "[SEND] SaveResult now (deferred) via HTTP /save_result" + tail
            if mode == 'both':
                return "[SEND] SaveResult now (deferred) via TCP+HTTP (cmd=0xBA0007 + HTTP /save_result)" + tail
            return "[SEND] SaveResult now (deferred) (cmd=0xBA0007)" + tail
        return '[SEND] SaveResult'

    def _is_dt_mode(self) -> bool:
        return int(getattr(self, 'max_slots', 6) or 6) == 3

    def _game_short_label(self) -> str:
        return 'DT' if self._is_dt_mode() else 'BAC'

    def _normal_auto_label(self) -> str:
        return f"{self._game_short_label()}_Auto Dispatch ({int(getattr(self, 'max_slots', 6) or 6)} slots)"

    def _dispatch_all_idle_label(self) -> str:
        return 'Dispatch All (burst)' if self._is_dt_mode() else 'Dispatch All'

    def _dispatch_all_running_label(self) -> str:
        return 'Stop Burst Dispatch' if self._is_dt_mode() else 'Stop Dispatch All'

    def _workflow_hint_text(self) -> str:
        if self._is_dt_mode():
            return 'Recommended test: click DT_Auto Dispatch (3 slots). Dispatch All (burst) fires 1→3→2 quickly for burst/manual testing.'
        return 'Recommended test: click BAC_Auto Dispatch (6 slots). Save Result normally happens before Stop Prediction.'

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
        on_cancel_result=None,
        max_slots: int = 6,
        on_toggle_latency=None,
    ):
        # slot count by game mode (6/3/1)
        self.max_slots = int(max_slots) if max_slots else 6

        # external callbacks
        self.on_start_pred    = on_start_pred
        self.on_stop_pred     = on_stop_pred
        self.on_dispatch_idx  = on_dispatch_idx
        self.on_toggle_dvr    = on_toggle_dvr
        self.on_mode_selected = on_mode_selected
        self.on_save_result   = on_save_result
        self.on_cancel_result = on_cancel_result

        # dispatch schedule config
        # NOTE: dispatch order is user-editable (default 1 3 2 4 5 6)
        _defaults_all = [1, 3, 2, 4, 5, 6]
        self.dispatch_all_seq = _defaults_all[: self.max_slots]
        self.dispatch_all_interval_var = tk.StringVar(value="0.5")   # seconds between indices (persisted; DT fallback becomes 0.3 only when no saved sidecar exists)
        self.save_gap_var              = tk.StringVar(value="9.9")   # seconds after last dispatch -> Save
        self.stop_gap_var              = tk.StringVar(value="10.0")  # seconds after last dispatch -> Stop
        self.dispatch_all_gap_var      = tk.StringVar(value="5.0")   # seconds between rounds
        self.round_skip_timeout_var     = tk.StringVar(value="60.0")  # BAC auto: skip stuck round after N seconds; 0 disables

        # state flags
        self._auto_loop         = False
        self._round_running     = False
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self._round_no          = 0
        self._last_dispatch_ts  = None  # wallclock seconds of last dispatch
        self._last_dispatch_idx = None  # last dispatched idx (debug / manual re-dispatch)
        self._manual_waiting_idx = None  # BAC manual: re-dispatch same idx until REAL card
        self._manual_stop_after = None  # tk after handle for delayed manual stop

        # BAC auto state
        self._dt_active = False
        self._dt_step = 0
        self._dt_waiting_for = None
        self._dt_timeout_after = None
        self._detected_flags = {i: False for i in range(1, self.max_slots + 1)}
        self._dt_card_values = {}  # idx -> real card class id, used by BAC drawing rules
        self._bac_batch_redispatch_after = None  # BAC Classic auto: periodic re-dispatch for pending batch indexes
        self._round_skip_timeout_after = None  # BAC/DT auto: watchdog for stuck current round
        self._round_skip_started_ts = None
        self._dt_finishing_current_round = False

        self.root = root
        root.title("BAC Dealer")

        # 20260121 latency mode
        self.on_toggle_latency = on_toggle_latency
        self._latency_mode = False

        # Status
        self.status_label = tk.Label(
            root, text="Waiting to be connected to Detector...",
            fg="red", font=("Arial", 12, "bold")
        )
        self.status_label.pack()

        # Mode banner (startup-only mode selection)
        self.mode_banner_var = tk.StringVar(value="")
        self.mode_banner_label = tk.Label(root, textvariable=self.mode_banner_var, fg="gray20", font=("Arial", 9))
        self.mode_banner_label.pack(pady=(0, 6))

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
        for txt, val in (("TCP", "tcp"), ("HTTP", "http"), ("Both", "both")):
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
        self.btn_start = tk.Button(btns, text="(+) Start New Round && Prediction", command=self._on_start_clicked)
        self.btn_start.pack(side=tk.LEFT, padx=4)

        # NOTE: wrap Stop so we can enforce a stop-gap even on manual click
        self.btn_save = tk.Button(btns, text="Save Result", command=self._on_save_clicked)
        self.btn_save.pack(side=tk.LEFT, padx=4)

        self.btn_stop_prediction = tk.Button(btns, text="Stop Prediction", command=self._on_stop_clicked)
        self.btn_stop_prediction.pack(side=tk.LEFT, padx=4)

        # Cancel Result is kept for legacy callback compatibility, but hidden in current workflow.
        self.btn_cancel = tk.Button(btns, text="Cancel Result", command=self._on_cancel_clicked)
        self.disable_save_result()  # enabled only after first AB0004
        self.disable_cancel_result()

        # Dispatch per index
        self.idx_frame = tk.Frame(root); self.idx_frame.pack(pady=(0, 4))
        self.disable_start_prediction()
        self.disable_stop_prediction()
        self.disable_dispatch_buttons()

        # Dispatch buttons are dynamically re-ordered by current ORDER
        self.dispatch_buttons = []
        for i in range(max_slots):
            b = tk.Button(self.idx_frame, text=f"Dispatch ?",
                          command=lambda: None,
                          state="disabled")
            b.grid(row=0, column=i, padx=2)
            self.dispatch_buttons.append(b)

        # Card slots
        cards = tk.Frame(root); cards.pack(pady=4)
        self.labels, self.slot_notes, self._cache = [], [], {}
        back_img = Image.open(CARDS_DIR / "back1.png").resize((CARD_W, CARD_H), Image.LANCZOS)
        back_photo = ImageTk.PhotoImage(back_img)
        for i in range(max_slots):
            cell = tk.Frame(cards)
            cell.grid(row=0, column=i, padx=2, pady=2)

            lbl = tk.Label(cell, image=back_photo, relief="solid", bd=1)
            lbl.image = back_photo
            lbl.pack()

            note = tk.Label(cell, text="", fg="gray25", font=("Arial", 8))
            note.pack(pady=(2, 0))

            self.labels.append(lbl)
            self.slot_notes.append(note)
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

        self.btn_dispatch_all = tk.Button(all_frame, text=self._dispatch_all_idle_label(), command=self.on_dispatch_all)
        self.btn_dispatch_all.pack(side=tk.LEFT)

        timeout_frame = tk.Frame(root); timeout_frame.pack(pady=(0, 2))
        tk.Label(timeout_frame, text="Skip current round when wait (s):").pack(side=tk.LEFT)
        _spin(timeout_frame, self.round_skip_timeout_var, w=6, frm=0.0, to=9999.0, inc=1.0).pack(side=tk.LEFT, padx=(6, 6))
        tk.Label(timeout_frame, text="0 = off", fg="gray35").pack(side=tk.LEFT)

        # ===== DT Auto row (separate from Dispatch All) =====
        dt_frame = tk.Frame(root); dt_frame.pack(pady=(2, 6))
        # Latency mode toggle (Index-1 only, stop on detection)
        self.btn_latency_mode = tk.Button(dt_frame, text="Latency Mode: OFF", command=self._toggle_latency_mode)
        self.btn_latency_mode.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_auto_dt = tk.Button(dt_frame, text=self._normal_auto_label(), command=self._toggle_auto_dt)
        self.btn_auto_dt.pack(side=tk.LEFT, padx=(0,10))
        tk.Label(dt_frame, text="Order:").pack(side=tk.LEFT, padx=(0,4))
        self.order_vars = []
        self._order_entries = []

        _defaults_all = ["1","3","2","4","5","6"]
        for _v in _defaults_all[: self.max_slots]:
            v = tk.StringVar(value=_v)
            self.order_vars.append(v)
            e = tk.Entry(dt_frame, width=2, textvariable=v)
            e.pack(side=tk.LEFT)
            self._order_entries.append(e)

        
        # When user edits ORDER:
        # - Let user type freely without auto-reverting.
        # - User must press Enter or click "Apply" to commit.
        for ent in self._order_entries:
            try:
                ent.bind("<Return>", lambda _e: self._on_order_changed(commit=True))
            except Exception:
                pass
        
        self.btn_apply_order = tk.Button(dt_frame, text="Apply", command=lambda: self._on_order_changed(commit=True))
        self.btn_apply_order.pack(side=tk.LEFT, padx=(8, 0))
        
        # Timeline hint
        self.timeline = tk.Label(root, text="", fg="gray25", font=("Arial", 9))
        self.timeline.pack(pady=(2, 2))

        self.workflow_hint = tk.Label(root, text=self._workflow_hint_text(), fg="gray35", font=("Arial", 9))
        self.workflow_hint.pack(pady=(0, 6))

        # ---- Scrollable Event Log (UNDER timeline) ----
        self._ui_log = ScrolledText(
            root,
            height=10,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self._ui_log.pack(fill="x", padx=10, pady=(0, 8))

        # Route ALL python logging to UI (DTMain / WS / TCP / DVR / GUI...)
        self._ui_log_handler = TkTextLogHandler(self, level=logging.INFO)
        logging.getLogger().addHandler(self._ui_log_handler)
        self._append_ui_log(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO [GUI] Event Log ready")

        # Load persisted gaps & order
        self._load_and_apply_saved()

        # Apply initial validated ORDER to dispatch buttons + idx->slot mapping
        self._on_order_changed(force=True)

        # Hotkeys
        root.bind("<+>",        lambda _e: self.btn_start.invoke())
        root.bind("<=>",        lambda _e: self.btn_start.invoke())
        root.bind("<KP_Add>",   lambda _e: self.btn_start.invoke())
        root.bind("<Return>",   lambda _e: self.btn_stop_prediction.invoke())

    # --------------- helpers / state ---------------
    def _append_ui_log(self, line: str) -> None:
        """Append one line into the scrollable UI log box (thread-safe)."""
        if not hasattr(self, "_ui_log") or self._ui_log is None:
            return

        def _do():
            try:
                self._ui_log.configure(state="normal")
                self._ui_log.insert("end", line + "\n")
                self._ui_log.see("end")
                self._ui_log.configure(state="disabled")
            except Exception:
                pass
            try:
                self._ui_log_file.write(line)
            except Exception:
                pass

        try:
            self.root.after(0, _do)
        except Exception:
            _do()

    def _set_slot_note(self, slot: int, text: str) -> None:
        """Set small text under a card slot (thread-safe)."""
        try:
            notes = getattr(self, 'slot_notes', None)
            if not notes or slot is None:
                return
            if not (0 <= int(slot) < len(notes)):
                return
            def _do():
                try:
                    notes[int(slot)].config(text=str(text))
                except Exception:
                    pass
            try:
                self.root.after(0, _do)
            except Exception:
                _do()
        except Exception:
            pass



    def _schedule_order_commit(self):
        """Debounced commit when leaving ORDER fields.
        If focus is still inside any ORDER entry, do nothing (user is still editing).
        """
        try:
            if getattr(self, "_order_commit_job", None) is not None:
                self.root.after_cancel(self._order_commit_job)
        except Exception:
            pass
        try:
            self._order_commit_job = self.root.after(200, self._commit_order_if_not_editing)
        except Exception:
            self._order_commit_job = None

    def _commit_order_if_not_editing(self):
        try:
            w = self.root.focus_get()
            if w in getattr(self, "_order_entries", []):
                return
        except Exception:
            pass
        self._on_order_changed(commit=True)
    def _try_parse_order_raw(self):
        """Return a valid order list (length N) if current entries form a valid permutation.

        If user is still typing (empty/duplicate/out-of-range/non-digit), return None.
        """
        N = int(getattr(self, "max_slots", 6) or 6)
        try:
            raw = [(v.get() or "").strip() for v in getattr(self, "order_vars", [])][:N]
        except Exception:
            return None

        if len(raw) != N:
            return None
        if any(not s for s in raw):
            return None
        if any(not s.isdigit() for s in raw):
            return None

        nums = [int(s) for s in raw]
        if any(n < 1 or n > N for n in nums):
            return None
        if len(set(nums)) != N:
            return None
        return nums

    def _validated_order(self):
        N = int(getattr(self, "max_slots", 6) or 6)
        default_all = [1, 3, 2, 4, 5, 6]
        default = default_all[:N]
        parsed = self._try_parse_order_raw()
        return parsed if parsed is not None else default
    def _apply_order_to_dispatch_buttons(self, order):
        """Apply ORDER to dispatch sequence only; keep visual slots fixed.

        Visual BAC table/card slots must match pydealerLight/game table index layout:
            column 1 -> idx1
            column 2 -> idx2
            column 3 -> idx3
            column 4 -> idx4
            column 5 -> idx5
            column 6 -> idx6

        ORDER is still kept for Dispatch All / burst sequence only. It must NOT reorder
        the visible buttons or card painting, otherwise idx2/idx3 appear reversed.
        """
        N = int(getattr(self, "max_slots", 6) or 6)
        order = list(order)[:N]
        self.dispatch_all_seq = order

        # Fixed visual mapping: prediction idx N always paints card slot N.
        self._idx_to_slot = {i: i - 1 for i in range(1, N + 1)}

        # Fixed button layout: Dispatch N is directly above card slot N.
        for col in range(min(N, len(self.dispatch_buttons))):
            idx = col + 1
            btn = self.dispatch_buttons[col]
            btn.config(text=f"Dispatch {idx}")
            btn.config(command=(lambda k=idx: self._dispatch_idx(k)))
            btn.grid(row=0, column=col, padx=2)

    def _on_order_changed(self, commit: bool = False, live: bool = True, force: bool = False):
        """Apply ORDER to internal mapping.

        - live=True: called on KeyRelease. Do NOT revert user input. Only apply when entries are
          already a full valid permutation.
        - commit=True: called on FocusOut/Enter. If invalid, revert to default.
        """
        N = int(getattr(self, "max_slots", 6) or 6)

        parsed = self._try_parse_order_raw()
        if live and (not commit) and (not force):
            # User is typing. Only apply when it becomes valid; never revert here.
            if parsed is None:
                return
            order = parsed
        else:
            # Commit/force path: fall back to default and repair UI.
            order = parsed if parsed is not None else self._validated_order()
            try:
                for v, n in zip(self.order_vars[:N], order):
                    v.set(str(n))
            except Exception:
                pass

        self._apply_order_to_dispatch_buttons(order)
        # Avoid spamming logs on every keypress.
        if commit or force:
            log.info("[ORDER] Applied order=%s", order)

    # --------------- re-dispatch loops    # --------------- re-dispatch loops (robust against detector repeating same output) ---------------
    def _cancel_auto_redispatch(self) -> None:
        """Cancel the repeating re-dispatch loop for BAC auto / Latency auto."""
        try:
            if getattr(self, "_auto_redispatch_after", None):
                self.root.after_cancel(self._auto_redispatch_after)
        except Exception:
            pass
        self._auto_redispatch_after = None
        self._auto_redispatch_idx = None
        self._auto_redispatch_expect_latency = None
        self._auto_redispatch_reason = None

    def _start_auto_redispatch(self, idx: int, reason: str, *, expect_latency: bool) -> None:
        """Start (or refresh) a repeating dispatch loop until waiting idx changes or round stops."""
        idx = int(idx)
        gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
        delay_ms = max(50, int(gap_s * 1000))

        # Refresh existing loop for the same idx/mode/reason
        self._auto_redispatch_idx = idx
        self._auto_redispatch_expect_latency = bool(expect_latency)
        self._auto_redispatch_reason = str(reason)

        # Cancel any previous scheduled tick to avoid stacking
        try:
            if getattr(self, "_auto_redispatch_after", None):
                self.root.after_cancel(self._auto_redispatch_after)
        except Exception:
            pass
        self._auto_redispatch_after = None

        def _tick():
            # Stop conditions
            if not getattr(self, "_dt_active", False):
                self._cancel_auto_redispatch()
                return
            if self.is_latency_mode() != self._auto_redispatch_expect_latency:
                self._cancel_auto_redispatch()
                return
            if not self._dt_is_waiting_for_idx(idx):
                self._cancel_auto_redispatch()
                return

            log.info("[LOOP] %s -> re-dispatch idx=%s (every %.2fs)", self._auto_redispatch_reason, idx, gap_s)
            self._dispatch_idx_force(idx)

            # schedule next tick
            try:
                self._auto_redispatch_after = self.root.after(delay_ms, _tick)
            except Exception:
                self._auto_redispatch_after = None

        log.info("[SCHED] %s -> start re-dispatch loop idx=%s in %.2fs", reason, idx, gap_s)
        try:
            self._auto_redispatch_after = self.root.after(delay_ms, _tick)
        except Exception:
            self._auto_redispatch_after = None

    def _dt_waiting_set(self):
        """Return the current auto-waiting indexes as a set of ints.

        Older DT/Latency flow stores one int in _dt_waiting_for. BAC Classic batch flow
        stores a set, for example {1, 3} or {2, 4}.
        """
        w = getattr(self, "_dt_waiting_for", None)
        if w is None:
            return set()
        if isinstance(w, (set, list, tuple)):
            out = set()
            for x in w:
                try:
                    out.add(int(x))
                except Exception:
                    pass
            return out
        try:
            return {int(w)}
        except Exception:
            return set()

    def _dt_is_waiting_for_idx(self, idx: int) -> bool:
        try:
            return int(idx) in self._dt_waiting_set()
        except Exception:
            return False

    def _bac_deal_order_key(self, idx: int) -> int:
        order = [1, 3, 2, 4, 5, 6]
        try:
            return order.index(int(idx))
        except Exception:
            return 999

    def _cancel_bac_batch_redispatch(self) -> None:
        """Cancel BAC Classic batch re-dispatch timer."""
        try:
            if getattr(self, "_bac_batch_redispatch_after", None):
                self.root.after_cancel(self._bac_batch_redispatch_after)
        except Exception:
            pass
        self._bac_batch_redispatch_after = None

    def _get_round_skip_timeout_s(self) -> float:
        """Return auto-round watchdog timeout seconds. 0 disables it."""
        return self._get_float(self.round_skip_timeout_var, 60.0, clamp_min=0.0)

    def _cancel_round_skip_timeout(self) -> None:
        """Cancel the stuck-round watchdog timer."""
        try:
            if getattr(self, "_round_skip_timeout_after", None):
                self.root.after_cancel(self._round_skip_timeout_after)
        except Exception:
            pass
        self._round_skip_timeout_after = None
        self._round_skip_started_ts = None

    def _schedule_round_skip_timeout(self, reason: str = "auto round") -> None:
        """Start a per-round watchdog.

        When BAC auto waits too long for a wrong/never-arriving required index,
        finish this round using the normal SaveResult -> StopPredict -> next-round flow
        so Auto Dispatch can continue instead of getting stuck forever.
        """
        self._cancel_round_skip_timeout()
        if not getattr(self, "_dt_active", False):
            return
        timeout_s = self._get_round_skip_timeout_s()
        if timeout_s <= 0:
            log.info("[WATCHDOG] Round skip timeout disabled (0=off)")
            return

        self._round_skip_started_ts = time.time()
        delay_ms = max(1, int(timeout_s * 1000))

        def _fire():
            self._round_skip_timeout_after = None
            if not getattr(self, "_dt_active", False):
                return
            if getattr(self, "_dt_finishing_current_round", False):
                return
            waited = 0.0
            try:
                waited = time.time() - float(self._round_skip_started_ts or time.time())
            except Exception:
                waited = timeout_s
            waiting = sorted(self._dt_waiting_set(), key=self._bac_deal_order_key)
            detected = dict(getattr(self, "_dt_card_values", {}) or {})
            log.warning(
                "[WATCHDOG] Current auto round waited %.1fs >= %.1fs; skip round now | waiting=%s detected_values=%s",
                waited, timeout_s, waiting, detected,
            )
            self._set_timeline(f"BAC: wait timeout {timeout_s:.0f}s -> skip current round")
            self._dt_finish_current_round(f"skipped after wait timeout {timeout_s:.0f}s")

        log.info("[WATCHDOG] Skip current round if waiting longer than %.1fs (%s)", timeout_s, reason)
        try:
            self._round_skip_timeout_after = self.root.after(delay_ms, _fire)
        except Exception:
            self._round_skip_timeout_after = None

    def _bac_pending_waiting_indices(self):
        """Indexes currently waited on but not yet returned as real cards."""
        vals = getattr(self, "_dt_card_values", {}) or {}
        pending = []
        for idx in self._dt_waiting_set():
            try:
                if idx not in vals or not self._is_real_bac_card(vals[idx]):
                    pending.append(int(idx))
            except Exception:
                pending.append(int(idx))
        pending.sort(key=self._bac_deal_order_key)
        return pending

    def _schedule_bac_batch_redispatch(self, reason: str = "pending batch") -> None:
        """Periodically re-dispatch all still-pending indexes in the current BAC batch.

        This is used only for BAC Classic auto mode. It avoids the old single-index loop,
        which cannot handle waiting for idx1+idx3 or idx2+idx4 at the same time.
        """
        if not getattr(self, "_dt_active", False):
            return
        if not self._is_bac_classic_mode():
            return
        if getattr(self, "_bac_batch_redispatch_after", None):
            return

        gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
        delay_ms = max(50, int(gap_s * 1000))

        def _tick():
            self._bac_batch_redispatch_after = None
            if not getattr(self, "_dt_active", False) or not self._is_bac_classic_mode():
                return
            pending = self._bac_pending_waiting_indices()
            if not pending:
                return
            log.info("[BAC] %s -> re-dispatch pending batch idx=%s (every %.2fs)", reason, pending, gap_s)
            for i in pending:
                self._dispatch_idx_force(int(i))
            # keep looping until every index in the batch has a real card
            self._schedule_bac_batch_redispatch(reason)

        log.info("[SCHED] BAC batch re-dispatch in %.2fs | waiting=%s", gap_s, sorted(self._dt_waiting_set(), key=self._bac_deal_order_key))
        try:
            self._bac_batch_redispatch_after = self.root.after(delay_ms, _tick)
        except Exception:
            self._bac_batch_redispatch_after = None

    def _dt_dispatch_indices(self, indices, reason: str = "BAC auto") -> None:
        """Dispatch one or more indexes immediately and wait for all of them.

        For BAC Classic this creates the requested batch behavior:
            [1, 3] together -> wait both
            [2, 4] together -> wait both
            [5] if needed -> wait
            [6] if needed -> wait
        """
        indices = [int(i) for i in indices if 1 <= int(i) <= int(getattr(self, "max_slots", 6) or 6)]
        if not indices:
            return

        self._dt_waiting_for = set(indices) if len(indices) > 1 else int(indices[0])
        for i in indices:
            try:
                self._detected_flags[int(i)] = False
            except Exception:
                pass

        if callable(self.on_dispatch_idx):
            log.info("[SEND] Dispatch (%s) idx=%s", reason, indices)
            for i in indices:
                self.on_dispatch_idx(int(i))
                self._last_dispatch_ts = time.time()
                self._last_dispatch_idx = int(i)
                try:
                    print("[DT-EVT] dispatch", int(i))
                except Exception:
                    pass

        try:
            if self._dt_timeout_after:
                self.root.after_cancel(self._dt_timeout_after)
                self._dt_timeout_after = None
        except Exception:
            pass

        # If detector returns cardback/empty or nothing, re-send only still-pending indexes.
        self._schedule_bac_batch_redispatch(reason)

    def _cancel_manual_redispatch(self) -> None:
        """Cancel repeating re-dispatch loop for BAC manual waiting idx."""
        try:
            if getattr(self, "_manual_redispatch_after", None):
                self.root.after_cancel(self._manual_redispatch_after)
        except Exception:
            pass
        self._manual_redispatch_after = None

    def _start_manual_redispatch(self, idx: int, reason: str) -> None:
        idx = int(idx)
        gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
        delay_ms = max(50, int(gap_s * 1000))

        try:
            if getattr(self, "_manual_redispatch_after", None):
                self.root.after_cancel(self._manual_redispatch_after)
        except Exception:
            pass
        self._manual_redispatch_after = None

        def _tick():
            if getattr(self, "_manual_waiting_idx", None) != idx:
                self._cancel_manual_redispatch()
                return
            log.info("[LOOP] %s -> re-dispatch idx=%s (every %.2fs)", reason, idx, gap_s)
            self._dispatch_idx_force(idx)
            try:
                self._manual_redispatch_after = self.root.after(delay_ms, _tick)
            except Exception:
                self._manual_redispatch_after = None

        log.info("[SCHED] %s -> start manual re-dispatch loop idx=%s in %.2fs", reason, idx, gap_s)
        try:
            self._manual_redispatch_after = self.root.after(delay_ms, _tick)
        except Exception:
            self._manual_redispatch_after = None

    def lock_mode_selector(self):
        for rb in self._mode_radios: rb.config(state="disabled")

    def set_status(self, txt: str, color: str = "Black"):
        # mirror UI text to log
        log.info("UI: %s", txt)

        # update status label
        try:
            self.status_label.config(text=txt, fg=color)
            self.root.update_idletasks()
        except Exception:
            pass

    def set_mode_banner(self, text: str) -> None:
        try:
            self.mode_banner_var.set(text)
        except Exception:
            pass

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
        # Lock ORDER while round is running to avoid mid-round mutations
        for ent in getattr(self, "_order_entries", []):
            try:
                ent.config(state="disabled")
            except Exception:
                pass

    def on_prediction_started(self):
        self._round_no += 1
        self._first_result_seen = False
        self.btn_start.config(state="disabled")
        self.btn_stop_prediction.config(state="normal")
        self._ready_to_dispatch = True
        self._last_dispatch_ts = None
        try:
            order = list(self._validated_order())[: self.max_slots]
        except Exception:
            order = [1, 3, 2, 4, 5, 6][: self.max_slots]
        log.info(
            "[ROUND] Prediction started | round=%s gm_base=%s mode=%s latency=%s order=%s dispatch_every=%s save_gap=%s stop_gap=%s gap=%s skip_timeout=%s",
            self._round_no,
            self.get_gm_base(),
            self.mode_var.get(),
            self.is_latency_mode(),
            order,
            (self.dispatch_all_interval_var.get() or ""),
            (self.save_gap_var.get() or ""),
            (self.stop_gap_var.get() or ""),
            (self.dispatch_all_gap_var.get() or ""),
            (self.round_skip_timeout_var.get() or ""),
        )

    def on_first_result(self):
        if not self._first_result_seen:
            self._first_result_seen = True
            self.enable_save_result()
            self.enable_cancel_result()

    def on_prediction_stopped(self):
        self.btn_stop_prediction.config(state="disabled")
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self.disable_save_result()
        self.disable_cancel_result()
        self._last_dispatch_ts = None
        self._set_timeline("")
        # Unlock ORDER when prediction stops (all modes)
        for ent in getattr(self, "_order_entries", []):
            try:
                ent.config(state="normal")
            except Exception:
                pass
        try:
            self._on_order_changed(live=True)
        except Exception:
            pass


    def on_round_ended(self):
        self.btn_start.config(state="disabled")
        self.btn_stop_prediction.config(state="disabled")
        for b in self.dispatch_buttons: b.config(state="disabled")
        self.enable_dispatch_all()
        self._round_running = False
        self._ready_to_dispatch = False
        self._first_result_seen = False
        self.disable_save_result()
        self.disable_cancel_result()
        self._last_dispatch_ts = None
        self._set_timeline("")
        # Unlock ORDER after round ends (all modes)
        for ent in getattr(self, "_order_entries", []):
            try:
                ent.config(state="normal")
            except Exception:
                pass
        # Re-validate and reflow dispatch buttons to match current ORDER
        try:
            self._on_order_changed(live=True)
        except Exception:
            pass


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
    def enable_cancel_result(self):     getattr(self, "btn_cancel", None) and self.btn_cancel.config(state="normal")
    def disable_cancel_result(self):    getattr(self, "btn_cancel", None) and self.btn_cancel.config(state="disabled")

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
    def update_card(self, idx: int, card_val: int) -> None:
        # Card-slot position is fixed by table slot/index, NOT by dispatch ORDER.
        # Example BAC Classic table layout: idx1, idx2, idx3, idx4, idx5, idx6 from left to right.
        slot = getattr(self, "_idx_to_slot", {1:0, 2:1, 3:2, 4:3, 5:4, 6:5}).get(int(idx))
        if slot is None:
            return

        # ---- cardback class 0 ----
        if int(card_val) == 0:
            # Ignore delayed non-real results for a BAC auto index that already has a real card.
            # Otherwise late cardback/empty responses can overwrite a successfully detected card image.
            try:
                vals = getattr(self, "_dt_card_values", {}) or {}
                if (not self.is_latency_mode()) and self._dt_active and self._is_bac_classic_mode() \
                        and (not self._dt_is_waiting_for_idx(int(idx))) \
                        and int(idx) in vals and self._is_real_bac_card(vals[int(idx)]):
                    log.info("[BAC] ignore stale cardback idx=%s; real value already stored=%s", int(idx), vals[int(idx)])
                    return
            except Exception:
                pass
            self._set_slot_note(slot, "CARDBACK (class=0)")
            key = "__BACKA__"
            if key not in self._cache:
                try:
                    img_path = CARDS_DIR / "backa.png"
                    if not img_path.exists():
                        img_path = CARDS_DIR / "back1.png"
                    pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
                    self._cache[key] = ImageTk.PhotoImage(pil_img)
                except Exception:
                    return

            self.labels[slot].config(image=self._cache[key])
            self.labels[slot].image = self._cache[key]
            self.root.update_idletasks()
            self.root.update()

            # Latency auto: cardback should trigger re-dispatch (idx1-only loop)
            try:
                if self.is_latency_mode() and self._dt_active and self._dt_waiting_for == int(idx) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_timeline(f"Latency: cardback -> re-dispatch idx{int(idx)}")
                    log.info("[LATENCY] cardback received idx=%s -> re-dispatch in %.2fs (Dispatch All every)", int(idx), gap_s)
                    self._start_auto_redispatch(int(idx), 'LATENCY cardback', expect_latency=True)
            except Exception:
                pass
            # BAC auto (event-driven): ignore cardback and keep re-dispatching pending idx until a REAL card arrives.
            try:
                if (not self.is_latency_mode()) and self._dt_active and self._dt_is_waiting_for_idx(int(idx)) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_slot_note(slot, "CARDBACK (ignored)")
                    self._set_timeline(f"BAC: cardback -> re-dispatch pending {sorted(self._dt_waiting_set(), key=self._bac_deal_order_key)}")
                    log.info("[BAC] cardback received idx=%s (ignored) -> re-dispatch pending batch in %.2fs", int(idx), gap_s)
                    if self._is_bac_classic_mode():
                        self._schedule_bac_batch_redispatch('BAC cardback')
                    else:
                        self._start_auto_redispatch(int(idx), 'DT cardback', expect_latency=False)
            except Exception:
                pass

            # BAC manual: ignore cardback and keep re-dispatching same idx until a REAL card arrives.
            try:
                if (not self.is_latency_mode()) and (not getattr(self, "_auto_loop", False)) and (not self._dt_active) and getattr(self, "_manual_waiting_idx", None) == int(idx) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_slot_note(slot, "CARDBACK (ignored)")
                    self._set_timeline(f"BAC: cardback -> re-dispatch idx{int(idx)}")
                    log.info("[BAC] manual cardback idx=%s (ignored) -> re-dispatch in %.2fs (Dispatch All every)", int(idx), gap_s)
                    self._start_manual_redispatch(int(idx), 'BAC manual cardback')
            except Exception:
                pass
            return

        # ---- empty class ----
        # Mapping rules:
        #   Latency: 0=cardback, 1=real, 2=empty
        #   DT/Baccarat: 0=cardback, 53 (and 99) = empty; other values are treated as real cards
        is_empty = False
        try:
            v = int(card_val)
            if self.is_latency_mode():
                is_empty = (v == 2) or (v not in (0, 1, 2))
            else:
                is_empty = (v in (53, 99))
        except Exception:
            is_empty = False

        if is_empty:
            # Ignore delayed non-real results for a BAC auto index that already has a real card.
            try:
                vals = getattr(self, "_dt_card_values", {}) or {}
                if (not self.is_latency_mode()) and self._dt_active and self._is_bac_classic_mode() \
                        and (not self._dt_is_waiting_for_idx(int(idx))) \
                        and int(idx) in vals and self._is_real_bac_card(vals[int(idx)]):
                    log.info("[BAC] ignore stale empty idx=%s; real value already stored=%s", int(idx), vals[int(idx)])
                    return
            except Exception:
                pass
            self._set_slot_note(slot, f"EMPTY (class={int(card_val)})")

            # show a neutral placeholder (back1) instead of mapping to a real card image
            key = "__EMPTY__"
            if key not in self._cache:
                try:
                    img_path = CARDS_DIR / "back1.png"
                    pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
                    self._cache[key] = ImageTk.PhotoImage(pil_img)
                except Exception:
                    self._cache[key] = None

            if self._cache.get(key) is not None:
                self.labels[slot].config(image=self._cache[key])
                self.labels[slot].image = self._cache[key]
                try:
                    self.root.update_idletasks()
                    self.root.update()
                except Exception:
                    pass

            # Latency auto: EMPTY should behave like CARDBACK -> keep re-dispatch idx1-only loop
            try:
                if self.is_latency_mode() and self._dt_active and self._dt_waiting_for == int(idx) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_timeline(f"Latency: empty -> re-dispatch idx{int(idx)}")
                    log.info("[LATENCY] empty received idx=%s -> re-dispatch in %.2fs (Dispatch All every)", int(idx), gap_s)
                    self._start_auto_redispatch(int(idx), 'LATENCY empty', expect_latency=True)
            except Exception:
                pass

            # BAC auto (event-driven): ignore EMPTY and keep re-dispatching pending idx until a REAL card arrives.
            try:
                if (not self.is_latency_mode()) and self._dt_active and self._dt_is_waiting_for_idx(int(idx)) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_slot_note(slot, "EMPTY (ignored)")
                    self._set_timeline(f"BAC: empty -> re-dispatch pending {sorted(self._dt_waiting_set(), key=self._bac_deal_order_key)}")
                    log.info("[BAC] empty received idx=%s (ignored) -> re-dispatch pending batch in %.2fs", int(idx), gap_s)
                    if self._is_bac_classic_mode():
                        self._schedule_bac_batch_redispatch('BAC empty')
                    else:
                        self._start_auto_redispatch(int(idx), 'DT empty', expect_latency=False)
            except Exception:
                pass

            # BAC manual: ignore EMPTY and keep re-dispatching same idx until a REAL card arrives.
            try:
                if (not self.is_latency_mode()) and (not getattr(self, "_auto_loop", False)) and (not self._dt_active) and getattr(self, "_manual_waiting_idx", None) == int(idx) and callable(self.on_dispatch_idx):
                    gap_s = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
                    self._set_slot_note(slot, "EMPTY (ignored)")
                    self._set_timeline(f"BAC: empty -> re-dispatch idx{int(idx)}")
                    log.info("[BAC] manual empty idx=%s (ignored) -> re-dispatch in %.2fs (Dispatch All every)", int(idx), gap_s)
                    self._start_manual_redispatch(int(idx), 'BAC manual empty')
            except Exception:
                pass
            return

# ---- normal card mapping ----
        if   0  <= card_val <= 15: suit = "C"
        elif 16 <= card_val <= 31: suit = "D"
        elif 32 <= card_val <= 47: suit = "S"
        elif 48 <= card_val <= 63: suit = "H"
        else: return

        rank_num = card_val % 16
        if not (1 <= rank_num <= 13): return

        key = f"{suit}{rank_num:02d}"
        self._set_slot_note(slot, f"{key} (val={int(card_val)})")
        if key not in self._cache:
            try:
                img_path = CARDS_DIR / f"{key}.png"
                pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
                self._cache[key] = ImageTk.PhotoImage(pil_img)
            except Exception:
                return

        self.labels[slot].config(image=self._cache[key])
        self.labels[slot].image = self._cache[key]
        self.root.update_idletasks()
        self.root.update()

        # Remember real BAC/DT card values for event-driven Baccarat completion rules.
        try:
            if (not self.is_latency_mode()) and self._is_real_bac_card(card_val):
                self._dt_card_values[int(idx)] = int(card_val)
        except Exception:
            pass

        # BAC manual: clear waiting flag when a REAL card arrives for the last manual dispatch idx.
        try:
            if getattr(self, "_manual_waiting_idx", None) == int(idx):
                self._manual_waiting_idx = None
                self._cancel_manual_redispatch()
        except Exception:
            pass

        # Latency auto: ONLY when a REAL card arrives, schedule save/stop and end the idx1 loop.
        try:
            if self.is_latency_mode() and self._dt_active and self._dt_waiting_for == int(idx):
                # stop any pending re-dispatch loop now that a REAL card arrived
                self._cancel_auto_redispatch()
                # mark finished for latency-auto
                self._dt_waiting_for = None
                self._dt_step = len(getattr(self, "_dt_order3", [1]))

                save_gap = self._get_float(self.save_gap_var, 9.9, clamp_min=0.0)
                stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)
                gap_next = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)

                log.info("[LATENCY] Real card detected idx=%s -> schedule Save in %.2fs, Stop in %.2fs", int(idx), save_gap, stop_gap)
                self._set_timeline(f"Latency: real card -> Save@{save_gap:.1f}s | Stop@{stop_gap:.1f}s")

                # schedule Save
                if callable(self.on_save_result):
                    log.info("[SCHED] SaveResult in %.2fs (Save gap)", save_gap)
                    self.root.after(int(save_gap * 1000), lambda: (log.info(self._save_result_log_text("scheduled", save_gap=save_gap)), self.on_save_result())[1])

                # schedule Stop (after save with a small guard)
                stop_ms = int(stop_gap * 1000)
                if callable(self.on_stop_pred):
                    log.info("[SCHED] StopPredict in %.2fs (Stop gap)", stop_gap)
                    self.root.after(stop_ms, lambda: (log.info("[SEND] StopPredict now (scheduled) (cmd=0xBA0004) (Stop gap=%.2fs)", stop_gap), self.on_stop_pred())[1])
                    self.root.after(stop_ms + 5, self._save_from_ui)

                # next round
                def _next_round():
                    if not self._dt_active:
                        return
                    log.info("[LATENCY] Next round in %.2fs (Gap)", gap_next)
                    self.root.after(int(gap_next * 1000), self._dt_start_round if self._dt_active else (lambda: None))
                self.root.after(stop_ms + 50, _next_round)
                return
        except Exception:
            pass

        # BAC auto event-driven (ONLY for real value cards)
        try:
            self._detected_flags[int(idx)] = True
            if self._dt_active and self._dt_is_waiting_for_idx(int(idx)):
                # BAC Classic batch mode: remove this idx from the pending batch.
                if self._is_bac_classic_mode():
                    waiting = self._dt_waiting_set()
                    waiting.discard(int(idx))
                    self._dt_waiting_for = waiting if waiting else None
                    log.info("[BAC] detected idx=%s -> remaining pending=%s", int(idx), sorted(waiting, key=self._bac_deal_order_key))

                    if waiting:
                        # Still waiting for the other index in the current batch, e.g. idx1 done but idx3 pending.
                        self._schedule_bac_batch_redispatch('BAC batch still pending')
                        return

                    # Current batch is complete; move to the next Baccarat phase.
                    self._cancel_bac_batch_redispatch()
                    self._cancel_auto_redispatch()
                    if self._dt_timeout_after:
                        try:
                            self.root.after_cancel(self._dt_timeout_after)
                        except Exception:
                            pass
                        self._dt_timeout_after = None
                    self.root.after(1, self._dt_dispatch_next)
                    return

                # Legacy single-index DT / Latency behavior.
                self._cancel_auto_redispatch()
                if self.is_latency_mode():
                    self._dt_waiting_for = None
                    self._dt_step = len(getattr(self, "_dt_order3", [1]))
                    save_gap = self._get_float(self.save_gap_var, 9.9, clamp_min=0.0)
                    stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)
                    log.info("[LATENCY] real card received idx=%s -> schedule Save in %.2fs (Save gap), Stop in %.2fs (Stop gap)", int(idx), save_gap, stop_gap)
                    self._set_timeline(f"Latency: real card idx{int(idx)} | Save@{save_gap:.1f}s | Stop@{stop_gap:.1f}s")

                    if callable(self.on_save_result):
                        self.root.after(int(save_gap * 1000), lambda: (log.info(self._save_result_log_text("scheduled", save_gap=save_gap)), self.on_save_result())[1])

                    def _stop_then_persist():
                        if callable(self.on_stop_pred):
                            log.info("[SEND] StopPredict now (scheduled) (cmd=0xBA0004) (Stop gap=%.2fs)", stop_gap)
                            self.on_stop_pred()
                        try:
                            self._save_from_ui()
                        except Exception:
                            pass
                    # ensure stop happens after save if user set stop < save
                    stop_ms = int(stop_gap * 1000)
                    save_ms = int(save_gap * 1000)
                    if stop_ms < save_ms + 200:
                        stop_ms = save_ms + 200
                    self.root.after(stop_ms, _stop_then_persist)

                    # Next round after Gap(s)
                    gap = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)
                    log.info("[LATENCY] next round scheduled in %.2fs (Gap)", gap)
                    self.root.after(stop_ms + int(gap * 1000), lambda: (self._dt_start_round() if self._dt_active else None))
                else:
                    log.info("[DT] detected idx=%s -> advance to next", int(idx))
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

    # ===== Baccarat card-drawing rule helpers =====
    def _is_bac_classic_mode(self) -> bool:
        return (not self.is_latency_mode()) and int(getattr(self, "max_slots", 6) or 6) == 6

    def _is_real_bac_card(self, card_val) -> bool:
        try:
            v = int(card_val)
        except Exception:
            return False
        # BAC/DT convention: 0=cardback, 53/99=empty, real card IDs are all other valid card IDs.
        if v in (0, 53, 99):
            return False
        return self._bac_rank_from_classid(v) is not None

    def _bac_rank_from_classid(self, card_val):
        """Return card rank 1..13 using the same sparse 16-step mapping as update_card().

        Current UI image mapping treats class IDs as:
            C01..C13 = 1..13
            D01..D13 = 17..29
            S01..S13 = 33..45
            H01..H13 = 49..61
        so rank is class_id % 16. Invalid/cardback/empty values return None.
        """
        try:
            v = int(card_val)
        except Exception:
            return None
        if v in (0, 53, 99):
            return None
        rank = v % 16
        if 1 <= rank <= 13:
            return rank
        return None

    def _bac_point_from_classid(self, card_val):
        """Baccarat point value: A=1, 2..9=face value, 10/J/Q/K=0."""
        rank = self._bac_rank_from_classid(card_val)
        if rank is None:
            return None
        if rank == 1:
            return 1
        if 2 <= rank <= 9:
            return rank
        return 0

    def _bac_total(self, idx_a: int, idx_b: int):
        vals = getattr(self, "_dt_card_values", {}) or {}
        if idx_a not in vals or idx_b not in vals:
            return None
        pa = self._bac_point_from_classid(vals[idx_a])
        pb = self._bac_point_from_classid(vals[idx_b])
        if pa is None or pb is None:
            return None
        return (pa + pb) % 10

    def _bac_banker_draws_after_player_third(self, banker_total: int, player_third_point: int) -> bool:
        """Standard Baccarat banker third-card rule."""
        if banker_total <= 2:
            return True
        if banker_total == 3:
            return player_third_point != 8
        if banker_total == 4:
            return 2 <= player_third_point <= 7
        if banker_total == 5:
            return 4 <= player_third_point <= 7
        if banker_total == 6:
            return player_third_point in (6, 7)
        return False

    def _bac_next_required_indices(self):
        """Return the next BAC index batch that must be predicted.

        Table/index meaning:
            1 = Player card 1
            2 = Player card 2
            3 = Banker card 1
            4 = Banker card 2
            5 = Player card 3
            6 = Banker card 3

        Fast Baccarat auto flow:
            dispatch [1, 3] together -> wait both
            dispatch [2, 4] together -> wait both
            dispatch [5] only if Player draws
            dispatch [6] only if Banker draws
            [] means the round is complete
        """
        vals = getattr(self, "_dt_card_values", {}) or {}

        def _missing(indices):
            out = []
            for i in indices:
                if i not in vals or not self._is_real_bac_card(vals[i]):
                    out.append(i)
            return out

        # First physical deal batch: Player first + Banker first.
        miss = _missing([1, 3])
        if miss:
            return miss

        # Second physical deal batch: Player second + Banker second.
        miss = _missing([2, 4])
        if miss:
            return miss

        player_total = self._bac_total(1, 2)
        banker_total = self._bac_total(3, 4)
        if player_total is None or banker_total is None:
            return []

        # Natural 8/9: no third cards.
        if player_total in (8, 9) or banker_total in (8, 9):
            log.info("[BAC-RULE] Natural: player=%s banker=%s -> finish with idx1,3,2,4", player_total, banker_total)
            return []

        # Player draws on 0..5; stands on 6..7.
        player_draws = player_total <= 5
        if player_draws:
            if 5 not in vals or not self._is_real_bac_card(vals[5]):
                log.info("[BAC-RULE] player=%s banker=%s -> Player draws idx5", player_total, banker_total)
                return [5]

            p3 = self._bac_point_from_classid(vals[5])
            if p3 is None:
                return [5]
            banker_draws = self._bac_banker_draws_after_player_third(banker_total, p3)
            log.info(
                "[BAC-RULE] player=%s banker=%s player3=%s -> banker_draws=%s",
                player_total, banker_total, p3, banker_draws,
            )
        else:
            banker_draws = banker_total <= 5
            log.info(
                "[BAC-RULE] player=%s stands, banker=%s -> banker_draws=%s",
                player_total, banker_total, banker_draws,
            )

        if banker_draws:
            if 6 not in vals or not self._is_real_bac_card(vals[6]):
                return [6]

        return []

    def _bac_next_required_index(self):
        """Compatibility wrapper for older single-index code paths."""
        indices = self._bac_next_required_indices()
        return indices[0] if indices else None

    def _dt_finish_current_round(self, reason: str = "completed") -> None:
        """Schedule SaveResult, StopPredict, and next round for DT/BAC auto dispatch."""
        if getattr(self, "_dt_finishing_current_round", False):
            log.info("[BAC] Ignore duplicate finish request: %s", reason)
            return
        self._dt_finishing_current_round = True
        self._cancel_auto_redispatch()
        self._cancel_bac_batch_redispatch()
        self._cancel_round_skip_timeout()
        self._dt_waiting_for = None
        save_gap = self._get_float(self.save_gap_var, 9.9, clamp_min=0.0)
        stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)
        gap_next = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)

        log.info("[BAC] Auto round %s | detected_values=%s | Save in %.2fs, Stop in %.2fs", reason, getattr(self, "_dt_card_values", {}), save_gap, stop_gap)
        self._set_timeline(f"BAC: {reason} -> Save@{save_gap:.1f}s | Stop@{stop_gap:.1f}s")

        if callable(self.on_save_result):
            log.info("[SCHED] SaveResult in %.2fs (Save gap)", save_gap)
            self.root.after(int(save_gap * 1000), lambda: (log.info(self._save_result_log_text("scheduled", save_gap=save_gap)), self.on_save_result())[1])

        stop_ms = int(stop_gap * 1000)
        save_ms = int(save_gap * 1000)
        if stop_ms < save_ms + 200:
            stop_ms = save_ms + 200
            stop_gap = stop_ms / 1000.0

        if callable(self.on_stop_pred):
            log.info("[SCHED] StopPredict in %.2fs (Stop gap)", stop_gap)
            self.root.after(stop_ms, lambda: (log.info("[SEND] StopPredict now (scheduled) (cmd=0xBA0004) (Stop gap=%.2fs)", stop_gap), self.on_stop_pred())[1])
            self.root.after(stop_ms + 5, self._save_from_ui)

        def _next_round():
            if not self._dt_active:
                return
            log.info("[BAC] Next round in %.2fs (Gap)", gap_next)
            self.root.after(int(gap_next * 1000), self._dt_start_round if self._dt_active else (lambda: None))
        self.root.after(stop_ms + 50, _next_round)

    def _load_and_apply_saved(self):
        N = int(getattr(self, "max_slots", 6) or 6)
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
            # Respect saved sidecar/.env values whenever they exist.
            # Only fall back to 0.3 for DT when no persisted payload exists at all.
            _set(self.dispatch_all_interval_var, "DISPATCH_ALL_EVERY")
            _set(self.save_gap_var,              "SAVE_GAP",            "9.9")
            _set(self.stop_gap_var,              "STOP_GAP",            "10.0")
            _set(self.dispatch_all_gap_var,      "ROUND_GAP",           "5.0")
            _set(self.round_skip_timeout_var,     "ROUND_WAIT_TIMEOUT",  "60.0")
            try:
                # Validate ORDER from persisted state: must be N unique ints in [1..N]
                raw = vals.get("ORDER", [1, 3, 2, 4, 5, 6])
                order = []
                seen = set()
                for n in raw[:N]:
                    try:
                        n = int(n)
                    except Exception:
                        continue
                    if 1 <= n <= N and n not in seen:
                        order.append(n)
                        seen.add(n)
                if len(order) != N:
                    order = [1, 3, 2, 4, 5, 6][: self.max_slots]
                for i, n in enumerate(order[:N]):
                    self.order_vars[i].set(str(int(n)))
            except Exception:
                pass
        else:
            # No persisted sidecar/.env payload exists: DT burst default = 0.3s, otherwise keep classic 0.5s.
            try:
                if int(getattr(self, "max_slots", 6) or 6) == 3:
                    self.dispatch_all_interval_var.set("0.3")
                else:
                    self.dispatch_all_interval_var.set("0.5")
            except Exception:
                pass

    def _save_from_ui(self):
        N = int(getattr(self, "max_slots", 6) or 6)
        vals = {}
        def _get(var, key, dflt):
            try: vals[key] = float(var.get())
            except Exception: vals[key] = float(dflt)
        _get(self.dispatch_all_interval_var, "DISPATCH_ALL_EVERY", 0.3)
        _get(self.save_gap_var,              "SAVE_GAP",            9.9)
        _get(self.stop_gap_var,              "STOP_GAP",            10.0)
        _get(self.dispatch_all_gap_var,      "ROUND_GAP",           5.0)
        _get(self.round_skip_timeout_var,     "ROUND_WAIT_TIMEOUT",  60.0)
        try:
            # Save validated ORDER (N unique ints in [1..N])
            vals["ORDER"] = list(self._validated_order())[:N]
        except Exception:
            vals["ORDER"] = [1, 3, 2, 4, 5, 6][:N]
        try:
            PERSIST_PATH.write_text(json.dumps(vals), encoding="utf-8")
        except Exception:
            pass

    def empty_card(self, slot: int) -> None:
        """Reset a slot to the card back image."""
        try:
            img_path = CARDS_DIR / "back1.png"
            pil_img  = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
            back_img = ImageTk.PhotoImage(pil_img)
            self.labels[slot].config(image=back_img)
            self.labels[slot].image = back_img
        except Exception:
            pass
        self.root.update_idletasks()
        self.root.update()
        # (Removed the incorrect DT block that referenced undefined `idx`)

    # ===== BAC auto (event-driven; separate from Dispatch All) =====

    def _toggle_auto_dt(self) -> None:
        # Toggle the auto-dispatch new-round loop
        self._dt_active = not self._dt_active
        if self._dt_active:
            self._dt_waiting_for = None
            self._dt_step = 0
            self._dt_waiting_first_result = True
            self._dt_detected_flags = [False] * (self.max_slots + 1)  # idx 1..N used
            self._dt_card_values = {}
            self._dt_finishing_current_round = False

            self.btn_auto_dt.config(text="Stop Auto Dispatch New Round")
            self._dt_start_round()
        else:
            # stopped
            self._cancel_auto_redispatch()
            self._cancel_bac_batch_redispatch()
            self._cancel_round_skip_timeout()
            self._dt_waiting_for = None
            self._dt_step = 0
            self._dt_waiting_first_result = True
            self._dt_card_values = {}
            self._dt_finishing_current_round = False

            if self.is_latency_mode():
                self.btn_auto_dt.config(text="Latency Auto Dispatch (idx1 only)")
            else:
                self.btn_auto_dt.config(text=self._normal_auto_label())
    def _dt_start_round(self):
        if not self._dt_active:
            return

        if self.is_latency_mode():
            self._dt_order3 = [1]
        else:
            # BAC auto uses FULL 6-order (user-editable)
            try:
                order = list(self._validated_order())[: self.max_slots]
            except Exception:
                order = [1, 3, 2, 4, 5, 6][: self.max_slots]
            self._dt_order3 = order

        self._cancel_auto_redispatch()
        self._cancel_bac_batch_redispatch()
        self._cancel_round_skip_timeout()
        self._dt_finishing_current_round = False
        self._dt_step = 0
        self._dt_waiting_for = None
        self._dt_card_values = {}
        self._detected_flags = {i: False for i in range(1, int(getattr(self, "max_slots", 6) or 6) + 1)}
        if callable(self.on_start_pred):
            log.info("[SEND] StartPredict (BAC auto) | order=%s", getattr(self, "_dt_order3", []))
            self.on_start_pred()
        self._schedule_round_skip_timeout("new auto round")
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

        is_lat = self.is_latency_mode()

        # BAC Classic uses dynamic Baccarat drawing rules and batch dispatches:
        # [1,3] -> [2,4] -> optional [5] -> optional [6].
        if self._is_bac_classic_mode():
            indices = self._bac_next_required_indices()
            if not indices:
                self._dt_finish_current_round("Baccarat rule completed")
                return
            self._dt_dispatch_indices(indices, reason="BAC auto")
            return

        # DT / Latency: keep the old fixed-order single-index behavior.
        if self._dt_step >= len(getattr(self, "_dt_order3", [])):
            if is_lat:
                # Latency mode schedules save/stop on REAL card arrival inside update_card().
                return
            self._dt_finish_current_round("fixed order completed")
            return
        idx = int(self._dt_order3[self._dt_step])
        self._dt_waiting_for = int(idx)

        try:
            self._detected_flags[int(idx)] = False
        except Exception:
            pass

        if callable(self.on_dispatch_idx):
            log.info("[SEND] Dispatch (BAC/DT auto) idx=%s", int(idx))
            self.on_dispatch_idx(int(idx))
        self._last_dispatch_ts = time.time()
        self._last_dispatch_idx = int(idx)

        try:
            print("[DT-EVT] dispatch", int(idx))
        except Exception:
            pass

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
            log.info("[SEND] Dispatch idx=%s", idx)
            self.on_dispatch_idx(idx)
        self._last_dispatch_ts = time.time()

    def _dispatch_idx_force(self, idx: int):
        """Always send the packet (used by BAC auto)."""
        if callable(self.on_dispatch_idx):
            log.info("[SEND] Dispatch (force) idx=%s", idx)
            self.on_dispatch_idx(idx)
        self._last_dispatch_ts = time.time()
        self._last_dispatch_idx = int(idx)

    def _on_start_clicked(self):
        """Manual Start button -> validate ORDER, log, then call StartPredict."""
        # Apply/validate ORDER at click-time (user may have edited)
        try:
            self._on_order_changed(live=True)
        except Exception:
            pass
        try:
            order = list(self._validated_order())[: self.max_slots]
        except Exception:
            order = [1, 3, 2, 4, 5, 6][: self.max_slots]
        log.info("[SEND] StartPredict (manual) (cmd=0xBA0003) | order=%s", order)
        if callable(self.on_start_pred):
            self.on_start_pred()

    def _on_save_clicked(self):
        """Manual Save button -> log, then call SaveResult."""
        log.info(self._save_result_log_text("manual"))
        if callable(self.on_save_result):
            self.on_save_result()
        try:
            self._save_from_ui()
        except Exception:
            pass

    def _on_cancel_clicked(self):
        """Manual Cancel button -> send CancelResult without stopping round."""
        log.info("[SEND] CancelResult (manual) (cmd=0xBA0008)")
        if callable(self.on_cancel_result):
            self.on_cancel_result()

    def _on_stop_clicked(self):
        """Manual Stop button → enforce stop-gap from last dispatch."""
        # stop any pending re-dispatch loops
        self._cancel_auto_redispatch()
        self._cancel_bac_batch_redispatch()
        self._cancel_round_skip_timeout()
        self._cancel_manual_redispatch()
        stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)
        now = time.time()
        if self._last_dispatch_ts is not None:
            elapsed = now - self._last_dispatch_ts
            delay = max(0.0, stop_gap - elapsed)
        else:
            delay = 0.0

        if delay <= 0:
            log.info("[SEND] StopPredict now (manual click) (cmd=0xBA0004) (delay=0)")
            if callable(self.on_stop_pred): self.on_stop_pred()
            try: self._save_from_ui()
            except Exception: pass
            return

        # schedule delayed stop, debounce clicks
        if self._manual_stop_after:
            try: self.root.after_cancel(self._manual_stop_after)
            except Exception: pass
        self.disable_stop_prediction()
        log.info("[SCHED] StopPredict in %.2fs (manual) (cmd=0xBA0004) (Stop gap=%.2fs, elapsed=%.2fs)", delay, stop_gap, (now - self._last_dispatch_ts) if self._last_dispatch_ts else 0.0)
        self.set_status(f"Stop scheduled in {delay:.1f}s (respecting stop gap)…", color="blue")
        self._manual_stop_after = self.root.after(int(delay * 1000), self._fire_manual_stop)

    def _fire_manual_stop(self):
        self._manual_stop_after = None
        log.info("[EXEC] Manual StopPredict now")
        if callable(self.on_stop_pred): self.on_stop_pred()
        try: self._save_from_ui()          # ensure gaps persist on delayed stop
        except Exception: pass

    def on_dispatch_all(self):
        if getattr(self, "_round_running", False):
            return
        self._auto_loop = not getattr(self, "_auto_loop", False)
        self.btn_dispatch_all.config(text=self._dispatch_all_running_label() if self._auto_loop else self._dispatch_all_idle_label())
        if self._auto_loop:
            # ensure ORDER is validated + applied before starting
            self._on_order_changed(live=True)
            log.info("[ROUND] DispatchAll toggled ON")
            self._kickoff_round()
        else:
            log.info("[ROUND] DispatchAll toggled OFF")
            self._set_timeline("")

    def _kickoff_round(self):
        if not self._auto_loop: return
        # Use current validated ORDER for Dispatch-All
        try:
            self.dispatch_all_seq = list(self._validated_order())[: self.max_slots]
        except Exception:
            self.dispatch_all_seq = [1, 3, 2, 4, 5, 6][: self.max_slots]
        if callable(self.on_start_pred):
            log.info("[SEND] StartPredict (Dispatch All) | order=%s", self.dispatch_all_seq)
            self.on_start_pred()
        self._wait_and_schedule()

    def _deferred_save(self, max_wait_ms=3000, tick_ms=150):
        """Wait until first result is seen (or timeout) before saving."""
        waited = {"ms": 0}
        def _step():
            if self._first_result_seen or waited["ms"] >= max_wait_ms:
                if callable(self.on_save_result):
                    log.info(self._save_result_log_text("deferred", waited_ms=waited["ms"], first_result_seen=self._first_result_seen))
                    self.on_save_result()
                return
            waited["ms"] += tick_ms
            self.root.after(tick_ms, _step)
        _step()

    def _wait_and_schedule(self, tries: int = 0) -> None:
        if not self._auto_loop: return

        if self._ready_to_dispatch:
            # parse inputs
            interval = self._get_float(self.dispatch_all_interval_var, 0.5, clamp_min=0.05)
            save_gap = self._get_float(self.save_gap_var, 9.9, clamp_min=0.0)
            stop_gap = self._get_float(self.stop_gap_var, 10.0, clamp_min=0.0)

            delay_ms = max(50, int(interval * 1000))

            # dispatch indices (respect max_slots)
            seq = [i for i in self.dispatch_all_seq if int(i) <= self.max_slots]
            for step, idx in enumerate(seq):
                self.root.after(step * delay_ms, lambda i=idx: self._dispatch_idx(i))

            last_step_ms = len(seq) * delay_ms

            # if first round, ensure extra warmup buffer for Save (but keep Stop gap as chosen)
            extra = 0
            if self._round_no <= 1:
                extra = max(0, int(2000 - int(save_gap * 1000)))  # ensure first save >=2s after last dispatch

            save_ms = last_step_ms + int(save_gap * 1000) + extra
            stop_ms = last_step_ms + int(stop_gap * 1000)
            if stop_ms < save_ms + 200:
                stop_ms = save_ms + 200  # always stop after save with a small guard

            # Update timeline hint (and log)
            ts = f"Dispatch@0,{interval:.1f},{2*interval:.1f}" + ("…" if len(self.dispatch_all_seq) > 3 else "")
            self._set_timeline(f"{ts} | Save@{save_ms/1000:.1f}s | Stop@{stop_ms/1000:.1f}s")

            log.info(
                "[SCHED] DispatchAll: order=%s interval=%.2fs -> last_dispatch@%.2fs | Save in %.2fs (Save gap=%.2fs) | Stop in %.2fs (Stop gap=%.2fs)",
                self.dispatch_all_seq,
                interval,
                last_step_ms/1000.0,
                save_ms/1000.0,
                save_gap,
                stop_ms/1000.0,
                stop_gap,
            )

            # Save is deferred until first result (or timeout)
            if callable(self.on_save_result):
                log.info("[SCHED] SaveResult in %.2fs (Save gap=%.2fs)", save_ms/1000.0, save_gap)
                self.root.after(save_ms, self._deferred_save)

            # Schedule stop
            if callable(self.on_stop_pred):
                log.info("[SCHED] StopPredict in %.2fs (Stop gap=%.2fs)", stop_ms/1000.0, stop_gap)
                self.root.after(stop_ms, lambda: (log.info("[SEND] StopPredict now (scheduled) (cmd=0xBA0004) (Stop gap=%.2fs)", stop_gap) or self.on_stop_pred()))
                self.root.after(stop_ms + 5, self._save_from_ui)

            # Next round gap
            def _schedule_next():
                if not self._auto_loop: return
                gap = self._get_float(self.dispatch_all_gap_var, 5.0, clamp_min=0.0)
                self.root.after(int(max(0.0, gap) * 1000), self._kickoff_round)

            self.root.after(stop_ms + 50, _schedule_next)
            return

        # Retry ~5s waiting for start-prediction confirmation
        if tries >= 50:
            print("[GUI] start-prediction not confirmed, stopping Dispatch All")
            self._auto_loop = False
            self.btn_dispatch_all.config(text=self._dispatch_all_idle_label())
            self.enable_dispatch_all()
            self._set_timeline("")
            return

        self.root.after(100, lambda: self._wait_and_schedule(tries + 1))
    
    def _auto_dt_label(self) -> str:
        return "Latency Auto (idx1)" if self.is_latency_mode() else self._normal_auto_label()



    def _toggle_latency_mode(self) -> None:
        """Legacy hook (button is hidden by main.py). Keep for backward compatibility."""
        self.set_latency_mode(not self._latency_mode)
    def apply_latency_mode_ui(self) -> None:
        """Latency UI: idx1-only; do NOT destroy/blank DT UI parts."""
        if not getattr(self, "_latency_mode", False):
            return

        # Robust: support both names (some patched versions used dispatch_btns)
        btns = getattr(self, "dispatch_buttons", None) or getattr(self, "dispatch_btns", None) or []
        if not btns:
            return

        # IMPORTANT:
        # - Do NOT force idx1 to NORMAL here (startup stage buttons are disabled)
        # - Only force idx2-6 disabled
        for i, btn in enumerate(btns, start=1):
            if i != 1:
                try:
                    btn.config(state=tk.DISABLED)
                except Exception:
                    pass

        # Disable Dispatch All in latency mode
        try:
            self.btn_dispatch_all.config(state=tk.DISABLED)
        except Exception:
            pass
        # Keep Order editable even in latency mode (only lock while round is running)

        # Rename the BAC auto button (when not running auto)
        auto_btn = getattr(self, "btn_auto_dt", None) or getattr(self, "btn_dt_auto", None)
        if auto_btn is not None and not getattr(self, "_dt_active", False):
            auto_btn.config(text="Latency Auto Dispatch (idx1 only)")
        try:
            self.workflow_hint.config(text="Recommended test: click Latency Auto Dispatch (idx1 only).")
        except Exception:
            pass

    def set_latency_mode(self, enabled: bool) -> None:
        """Enable/disable latency behavior (chosen by Startup UI)."""
        self._latency_mode = bool(enabled)
        N = int(getattr(self, "max_slots", 6) or 6)

        # --- Fix "Order only shows 1" broken state automatically ---
        default_order = ["1", "3", "2", "4", "5", "6"]
        if hasattr(self, "order_vars") and isinstance(self.order_vars, list) and len(self.order_vars) >= N:
            cur = [(v.get() or "").strip() for v in self.order_vars[:N]]
            # Repair if any blanks OR only first slot is filled
            if (cur.count("") > 0) or (sum(1 for x in cur if x) <= 1):
                for v, dv in zip(self.order_vars[:N], default_order):
                    v.set(dv)

        # Robust: support both names (some patched versions used dispatch_btns)
        btns = getattr(self, "dispatch_buttons", None) or getattr(self, "dispatch_btns", None) or []
        auto_btn = getattr(self, "btn_auto_dt", None) or getattr(self, "btn_dt_auto", None)

        if self._latency_mode:
            self.apply_latency_mode_ui()
        else:
            # Restore DT mode:
            # Make idx2-6 match idx1 state (so we don't accidentally enable early)
            if btns:
                try:
                    state1 = btns[0].cget("state")
                except Exception:
                    state1 = tk.DISABLED
                for b in btns[1:]:
                    try:
                        b.config(state=state1)
                    except Exception:
                        pass

            # Restore Dispatch All
            try:
                self.btn_dispatch_all.config(state=tk.NORMAL, text=self._dispatch_all_idle_label())
            except Exception:
                pass

            try:
                self.workflow_hint.config(text=self._workflow_hint_text())
            except Exception:
                pass

            # Unlock order entries
            for ent in getattr(self, "_order_entries", []):
                try:
                    ent.config(state="normal")
                except Exception:
                    pass

            # Restore BAC auto button label (when not running auto)
            if auto_btn is not None and not getattr(self, "_dt_active", False):
                auto_btn.config(text=self._normal_auto_label())

    def is_latency_mode(self) -> bool:
        return bool(getattr(self, "_latency_mode", False))
