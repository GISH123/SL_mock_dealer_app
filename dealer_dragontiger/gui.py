# dealer_dragontiger/gui.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from pathlib import Path
import os

CARDS_DIR = Path(__file__).resolve().parent.parent / "card_shown_ui" / "greywyvern-cardset"

RANKS = "A23456789TJQK"
SUITS = "CDHS"       # ♣ ♦ ♥ ♠  (order used by card_shown_ui file-names)

CARD_W, CARD_H = 80, 120  # px

def _card_png(rank: int, suit: int) -> str:
    """
    Greywyvern-cardset filenames look like  C01.png  H13.png  S08.png …
                         suit-letter first ░░██       ██
                                            │        │
                                            └─ 2-digit rank 01-13
    `rank` ·0-12  (A=0, …, K=12)
    `suit` ·0-3   (C=0, D=1, H=2, S=3)
    """
    SUIT_LETTERS = "CDHS"        # clubs ♦ hearts ♠
    return os.path.join(CARDS_DIR, f"{SUIT_LETTERS[suit]}{rank+1:02d}.png")

class DealerGUI:
    """
    Pure-Tkinter UI:
        • status             (Label)
        • Start-/Stop/Dispatch buttons
        • six card slots     (Labels)

    All heavy work (asyncio, sockets) is done in DragonTigerApp; GUI is
    called only from the Tk thread.
    """
    def __init__(
        self,
        root: tk.Tk,
        *,
        on_start_pred,
        on_stop_pred,
        on_dispatch_idx,          # callable(idx:int)
        max_slots: int = 6,
    ):
        self.root = root
        root.title("Dragon-Tiger Dealer")

        # Status line
        self.status_label = tk.Label(root, text="Waiting to be connected to Detector...", fg="red", font=("Arial", 12, "bold"))
        self.status_label.pack()

        # Control buttons
        btns = tk.Frame(root)
        btns.pack(pady=4)

        self.btn_start = tk.Button(      # combined button
            btns,
            text="(+) Start New Round && Prediction",
            command=on_start_pred
        )
        self.btn_start.pack(side=tk.LEFT, padx=4)

        # Stop Prediction
        self.btn_stop_prediction = tk.Button(
            btns, text="Stop Prediction", command=on_stop_pred
        )
        self.btn_stop_prediction.pack(side=tk.LEFT, padx=4)

        # Dispatch buttons
        self.idx_frame = tk.Frame(root)
        self.idx_frame.pack(pady=(0, 4))

        # disable them initially
        self.disable_start_prediction()
        self.disable_stop_prediction()
        self.disable_dispatch_buttons()

        ORDER = [1, 3, 2, 4, 5, 6][:max_slots]          # index-to-GUI order
        self.dispatch_buttons = []
        for col, idx in enumerate(ORDER):
            b = tk.Button(self.idx_frame, text=f"Dispatch {idx}",
                        command=lambda k=idx: on_dispatch_idx(k),
                        state="disabled")
            b.grid(row=0, column=col, padx=2)
            self.dispatch_buttons.append(b)

        # ------------------------------------------------------------------------
        #  card slots – create a frame, then six empty labels
        # ------------------------------------------------------------------------
        cards = tk.Frame(root)                     #  ←  ADD this line
        cards.pack(pady=4)                         #  ←  …and this line

        self.labels  = []
        self._cache  = {}                          # cache for loaded PNGs

        for i in range(max_slots):
            img = Image.open(CARDS_DIR / "back1.png").resize((CARD_W, CARD_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(cards, image=photo, relief="solid", bd=1)
            lbl.image = photo  # keep reference to prevent garbage collection
            lbl.grid(row=0, column=i, padx=2, pady=2)
            self.labels.append(lbl)

        # Bind “+” and “Enter” keys
        root.bind("+",    lambda _e: self.btn_start.invoke())   # “+” ==> start
        root.bind("<Return>", lambda _e: self.btn_stop.invoke())# Enter ==> stop

    # --- Status update ---
    def set_status(self, txt: str, color: str = "Black"):
        """Update status text & color."""
        self.status_label.config(text=txt, fg=color)
        self.root.update_idletasks()

    # --- Connection state ---
    def on_connected(self):
        """Call when TCP connected."""
        self.set_status("Connected", "green")
        self.btn_new_round.config(state="normal")

    # --- Round control ---
    def on_round_started(self):
        """Enable prediction & dispatch buttons at round start."""
        self.btn_start.config(state="normal")
        for b in self.dispatch_buttons:
            b.config(state="normal")

    def on_prediction_started(self):
        """Enable Stop Prediction, disable Start Prediction."""
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

    def on_prediction_stopped(self):
        """Disable Stop Prediction, keep dispatch buttons enabled until round end."""
        self.btn_stop.config(state="disabled")

    def on_round_ended(self):
        """Disable prediction & dispatch after round ends."""
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        for b in self.dispatch_buttons:
            b.config(state="disabled")

    # ==========================================================
    def disable_start_prediction(self): self.btn_start.config(state="disabled")
    def enable_start_prediction (self): self.btn_start.config(state="normal")

    def enable_stop_prediction(self):
        self.btn_stop_prediction.config(state="normal")

    def disable_stop_prediction(self):
        self.btn_stop_prediction.config(state="disabled")

    def enable_dispatch_buttons(self):
        for child in self.idx_frame.winfo_children():
            child.config(state="normal")

    def disable_dispatch_buttons(self):
        for child in self.idx_frame.winfo_children():
            child.config(state="disabled")
    # ==========================================================

    def update_card(self, idx: int, card_val: int) -> None:
        """
        slot 0–5 mapping to index 1–6, card_val mapping according to GetCardVal()
        """
        print(f"[GUI] update_card() called: idx={idx}, card_val={card_val}")

        # Dragon-Tiger camera returns card-box order 1-3-2-4-5-6.
        ORDER_MAP = {1: 0, 3: 1, 2: 2, 4: 3, 5: 4, 6: 5}  # index → GUI slot
        slot = ORDER_MAP.get(idx)
        if slot is None:        # unknown index, ignore safely
                print(f"[GUI] Slot {slot} out of range, ignoring.")
                return

        # ---------------- Decode suit & rank ----------------
        if   0  <= card_val <= 15:  suit = "C"  # Clubs
        elif 16 <= card_val <= 31:  suit = "D"  # Diamonds
        elif 32 <= card_val <= 47:  suit = "S"  # Spades
        elif 48 <= card_val <= 63:  suit = "H"  # Hearts
        else:
            print(f"[GUI] Invalid card_val: {card_val}")
            return

        rank_num = card_val % 16  # 1–13 range
        if not (1 <= rank_num <= 13):
            print(f"[GUI] Invalid rank {rank_num} from card_val {card_val}")
            return
        rank_str = f"{rank_num:02d}"  # zero-padded for filenames

        key = f"{suit}{rank_str}"  # e.g., C01, D13
        # -----------------------------------------------------

        if key not in self._cache:
            try:
                img_path = CARDS_DIR / f"{key}.png"
                pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
                self._cache[key] = ImageTk.PhotoImage(pil_img)
                print(f"[GUI] Image loaded and cached: {key}")
            except Exception as e:
                print(f"[GUI] Failed to load image '{key}': {e}")
                return

        # Apply image
        self.labels[slot].config(image=self._cache[key])
        self.labels[slot].image = self._cache[key]  # prevent garbage collection

        # Force Tkinter to refresh the UI
        self.root.update_idletasks()
        self.root.update()            # <- this makes UI immediately repaint

    def empty_card(self, slot: int) -> None:
        """
        Reset slot to card back image
        """
        try:
            img_path = CARDS_DIR / "back1.png"
            pil_img = Image.open(img_path).resize((CARD_W, CARD_H), Image.LANCZOS)
            back_img = ImageTk.PhotoImage(pil_img)
            self.labels[slot].config(image=back_img)
            self.labels[slot].image = back_img  # prevent garbage collection
            print(f"[GUI] Slot {slot} reset to back image.")
        except Exception as e:
            print(f"[GUI] Failed to load back image: {e}")

        self.root.update_idletasks()
        self.root.update()            # <- this makes UI immediately repaint

