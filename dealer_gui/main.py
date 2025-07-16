import os, asyncio, struct, tkinter as tk
from tkinter import Button, Entry, Label, Toplevel, scrolledtext
from datetime import datetime
from pathlib import Path
# --- PyInstaller bootstrap ------------------------------------
import os, sys
from pathlib import Path
from dotenv import load_dotenv
import socket
from tkinter import ttk
import time

if hasattr(sys, "_MEIPASS"):
    # Running from dist/dealer_gui_exec/
    ROOT = Path(sys.executable).resolve().parent.parent
else:
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config.env", override=True)
# --------------------------------------------------------------

MSG_HUB_IP   = os.environ["MSG_HUB_SERVICE_IP"]
MSG_HUB_PORT = int(os.environ["MSG_HUB_SERVICE_PORT"])

DVR_TARGET_IP   = os.environ["DVR_TARGET_IP"]
DVR_TARGET_PORT = int(os.environ["DVR_TARGET_PORT"])

from utils.logging_utils import init_logger
logger = init_logger("dealer_gui")
# …rest of your GUI code (prints → log.info) …

logger.info(f"[dealer_gui] 🎯 Target is {MSG_HUB_IP}:{MSG_HUB_PORT}")

# ── protocol constants (unchanged) ──────────────────────────────────
CMD_INPUTJSON    = 0x32001
CMD_SCENE_SWITCH = 0x31001
CMD_START_RECORD = 0x20001
CMD_STOP_RECORD  = 0x20002
CMD_START_PLACE  = 0x20003
CMD_STOP_PLACE   = 0x20004

def log(widget, msg):
    widget.insert(tk.END, f"[{datetime.now().isoformat()}] {msg}\n")
    widget.see(tk.END)
    logger.info(f"[{datetime.now().isoformat()}] {msg}\n")

class FMRouteWindow:
    def __init__(self, parent):
        win = Toplevel(parent)
        win.title("FMRoute Manual")
        self.root = win

        Label(win, text="Table").pack()
        self.table = Entry(win, width=12)
        self.table.insert(0, "B001")
        self.table.pack()

        Label(win, text="Device ID").pack()
        self.devid = Entry(win, width=12)
        self.devid.insert(0, "obs")
        self.devid.pack()

        Label(win, text="Stream ID").pack()
        self.stream = Entry(win, width=12)
        self.stream.insert(0, "OBSxS")
        self.stream.pack()

        Label(win, text="Scene Name").pack()
        self.scene = Entry(win, width=40)
        self.scene.insert(0, "Near")
        self.scene.pack()

        Label(win, text="Input Name").pack()
        self.inputname = Entry(win, width=40)
        self.inputname.insert(0, "{header:json,body:[card_index:1,3,4,5,6],sceneName:Near}")
        self.inputname.pack()

        Label(win, text="→ InputJSON").pack()
        Button(win, text="GET /inputjson", command=lambda: self.send("GET", "inputjson")).pack()
        Button(win, text="POST /inputjson", command=lambda: self.send("POST", "inputjson")).pack()

        Label(win, text="→ Scene").pack()
        Button(win, text="GET /scene", command=lambda: self.send("GET", "scene")).pack()
        Button(win, text="POST /scene", command=lambda: self.send("POST", "scene")).pack()

        self.log = scrolledtext.ScrolledText(win, height=6, width=80)
        self.log.pack()

    def send(self, method, route):
        # 🔍 Log raw values before encoding
        log(self.log, f"[FMRoute] Preparing to send:")
        log(self.log, f"  method = {method}")
        log(self.log, f"  route  = {route}")
        log(self.log, f"  table  = {self.table.get()}")
        log(self.log, f"  devid  = {self.devid.get()}")
        log(self.log, f"  stream = {self.stream.get()}")
        if route == "inputjson":
            log(self.log, f"  inputName = {self.inputname.get()}")
        else:
            log(self.log, f"  sceneName = {self.scene.get()}")

        CMD = CMD_INPUTJSON if route == "inputjson" else CMD_SCENE_SWITCH
        table = self.table.get().encode()[:4].ljust(4, b"\0")
        devid = self.devid.get().encode()[:4].ljust(4, b"\0")
        streamid = self.stream.get().encode()[:12].ljust(12, b"\0")
        payload = self.inputname.get().encode() if CMD == CMD_INPUTJSON else self.scene.get().encode()
        pkt = struct.pack("!I I I 4s 4s 12s H", CMD, 34 + 1 + len(payload), 1, table, devid, streamid, len(payload))
        method_flag = b"\x01" if method == "POST" else b"\x00"
        pkt += method_flag + payload

        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt.hex()}")
                log(self.log, f"[FMRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, "[FMRoute] ✅ Sent")
            except Exception as e:
                log(self.log, f"[FMRoute] ❌ Error: {e}")

        asyncio.get_event_loop().run_until_complete(task())

class DVRRouteWindow:
    def __init__(self, parent):
        self.root = Toplevel(parent)
        self.root.title("DVR Manual Control")

        Label(self.root, text="Table").pack()
        self.table_entry = Entry(self.root, width=8)
        self.table_entry.insert(0, "T032")
        self.table_entry.pack()

        Label(self.root, text="Gmcode").pack()
        self.gmcode_entry = Entry(self.root, width=16)
        self.gmcode_entry.insert(0, "testg001")
        self.gmcode_entry.pack()

        # Frame for Start Record + Combo Button
        f_start = tk.Frame(self.root)
        f_start.pack(fill="x", padx=10, pady=3)
        Button(f_start, text="Start Record", command=lambda: self.send(CMD_START_RECORD)).pack(side="left", expand=True, fill="x")
        Button(f_start, text="▶ Start Both", command=self.send_start_both).pack(side="left", padx=6)

        # Frame for Stop Record
        Button(self.root, text="Stop Record", command=lambda: self.send(CMD_STOP_RECORD)).pack(fill="x", padx=10, pady=3)

        # Frame for Start Place
        Button(self.root, text="Start Place", command=lambda: self.send(CMD_START_PLACE)).pack(fill="x", padx=10, pady=3)

        # Frame for Stop Place + Combo Button
        f_stop = tk.Frame(self.root)
        f_stop.pack(fill="x", padx=10, pady=3)
        Button(f_stop, text="Stop Place", command=lambda: self.send(CMD_STOP_PLACE)).pack(side="left", expand=True, fill="x")
        Button(f_stop, text="■ Stop Both", command=self.send_stop_both).pack(side="left", padx=6)

        # # Frame for double-packet testing
        # f_double = tk.Frame(self.root)
        # f_double.pack(fill="x", padx=10, pady=3)
        # Button(f_double, text="🔁 Double Start Record", command=lambda: self.send_double_record(CMD_START_RECORD)).pack(side="left", expand=True, fill="x", padx=2)
        # Button(f_double, text="🔁 Double Stop Record", command=lambda: self.send_double_record(CMD_STOP_RECORD)).pack(side="left", expand=True, fill="x", padx=2)

        self.log = scrolledtext.ScrolledText(self.root, height=6, width=80)
        self.log.pack()
        # Frame for custom double packet
        f_custom = tk.LabelFrame(self.root, text="Custom Double Packet → DVR Direct", padx=10, pady=5)
        f_custom.pack(fill="x", padx=10, pady=5)

        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record":  CMD_STOP_RECORD,
            "Start Place":  CMD_START_PLACE,
            "Stop Place":   CMD_STOP_PLACE,
        }

        Label(f_custom, text="Command 1").grid(row=0, column=0, padx=5, pady=3)
        self.cmd1_var = tk.StringVar(value="Start Record")
        cmd1_menu = ttk.Combobox(f_custom, textvariable=self.cmd1_var, values=list(cmd_options.keys()), state="readonly")
        cmd1_menu.grid(row=0, column=1, padx=5)

        Label(f_custom, text="Command 2").grid(row=1, column=0, padx=5, pady=3)
        self.cmd2_var = tk.StringVar(value="Start Place")
        cmd2_menu = ttk.Combobox(f_custom, textvariable=self.cmd2_var, values=list(cmd_options.keys()), state="readonly")
        cmd2_menu.grid(row=1, column=1, padx=5)

        Button(f_custom, text="Send Custom Double", command=lambda: self.send_double_custom(cmd_options)).grid(row=0, column=2, rowspan=2, padx=10, pady=3)

        # Frame for 10x Loop Test
        # Inside f_custom
        Button(f_custom, text="▶ Start 10x Loop Test (Command 1)", command=self.start_10x_loop)\
            .grid(row=2, column=0, columnspan=2, pady=4)
        Button(f_custom, text="▶ Start 10x Mixed Test (Command 1 then Command 2)", command=self.start_10x_mixed_loop)\
            .grid(row=2, column=2, pady=4)

        # Frame for Gmcode Loop Test
        f_loop_gmcode = tk.LabelFrame(self.root, text="Loop Gmcode test, four command", padx=10, pady=5)
        f_loop_gmcode.pack(fill="x", padx=10, pady=5)

        Button(f_loop_gmcode, text="▶ Start Full 5-Round Game Loop", command=self.start_gmcode_loop).pack(pady=3)

    def send_start_both(self):
        # self.send(CMD_START_RECORD)
        # self.send(CMD_START_PLACE)
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt_start_record = struct.pack("!I I H 4s 16s", CMD_START_RECORD, 30, 1, table, gmcode)

        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt_start_place = struct.pack("!I I H 4s 16s", CMD_START_PLACE, 30, 1, table, gmcode)

        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt_start_record.hex()}")
                log(self.log, f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt_start_record)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DVRRoute] ✅ Sent DVR cmd=0x{CMD_START_RECORD:X}")
            except Exception as e:
                log(self.log, f"[DVRRoute] ❌ {e}")
        asyncio.get_event_loop().run_until_complete(task())
        
        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt_start_place.hex()}")
                log(self.log, f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt_start_place)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DVRRoute] ✅ Sent DVR cmd=0x{CMD_START_PLACE:X}")
            except Exception as e:
                log(self.log, f"[DVRRoute] ❌ {e}")
        asyncio.get_event_loop().run_until_complete(task())

    def send_stop_both(self):
        # self.send(CMD_STOP_RECORD)
        # self.send(CMD_STOP_PLACE)
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt_stop_record = struct.pack("!I I H 4s 16s", CMD_STOP_RECORD, 30, 1, table, gmcode)

        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt_stop_place = struct.pack("!I I H 4s 16s", CMD_STOP_PLACE, 30, 1, table, gmcode)

        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt_stop_record.hex()}")
                log(self.log, f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt_stop_record)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DVRRoute] ✅ Sent DVR cmd=0x{CMD_STOP_RECORD:X}")
            except Exception as e:
                log(self.log, f"[DVRRoute] ❌ {e}")
        asyncio.get_event_loop().run_until_complete(task())
        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt_stop_place.hex()}")
                log(self.log, f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt_stop_place)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DVRRoute] ✅ Sent DVR cmd=0x{CMD_STOP_PLACE:X}")
            except Exception as e:
                log(self.log, f"[DVRRoute] ❌ {e}")
        asyncio.get_event_loop().run_until_complete(task())

    def send_double_record(self, CMD1, CMD2):
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        
        pkt1 = struct.pack("!I I H 4s 16s", CMD1, 30, 1, table, gmcode)
        pkt2 = struct.pack("!I I H 4s 16s", CMD2, 30, 1, table, gmcode)
        double_pkt = pkt1 + pkt2  # 60 bytes

        log(self.log, f"[DVRRoute] Sending 2x DVR packets (cmd=0x{CMD1:X}, 0x{CMD2:X}) via socket.sendall()")
        log(self.log, f"[DEBUG] 60-byte hex = {double_pkt.hex()}")

        try:
            resp = self.send_directly(double_pkt)
            if resp:
                log(self.log, f"[DVR → DIRECT] ← Response: {resp.hex()}")
            else:
                log(self.log, f"[DVR → DIRECT] ❌ No response received")
        except Exception as e:
            log(self.log, f"[DVRRoute] ❌ {e}")

    def send_double_custom(self, cmd_options):
        name1 = self.cmd1_var.get()
        name2 = self.cmd2_var.get()
        CMD1 = cmd_options[name1]
        CMD2 = cmd_options[name2]

        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")

        pkt1 = struct.pack("!I I H 4s 16s", CMD1, 30, 1, table, gmcode)
        pkt2 = struct.pack("!I I H 4s 16s", CMD2, 30, 1, table, gmcode)
        double_pkt = pkt1 + pkt2

        log(self.log, f"[DVR → DIRECT] Sending to {DVR_TARGET_IP}:{DVR_TARGET_PORT}")
        log(self.log, f"[DVR → DIRECT] Sending 2x packets (0x{CMD1:X}, 0x{CMD2:X})")
        log(self.log, f"[DEBUG] 60-byte hex = {double_pkt.hex()}")

        try:
            resp = self.send_directly(double_pkt)
            if resp:
                log(self.log, f"[DVR → DIRECT] ← Response: {resp.hex()}")
            else:
                log(self.log, f"[DVR → DIRECT] ❌ No response received")
        except Exception as e:
            log(self.log, f"[DVR → DIRECT] ❌ {e}")

    def start_10x_loop(self):
        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record":  CMD_STOP_RECORD,
            "Start Place":  CMD_START_PLACE,
            "Stop Place":   CMD_STOP_PLACE,
        }
        CMD = cmd_options[self.cmd1_var.get()]
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt = struct.pack("!I I H 4s 16s", CMD, 30, 1, table, gmcode)

        def loop():
            for i in range(10):
                log(self.log, f"[Loop] Round {i+1}/10 — sending {self.cmd1_var.get()} (0x{CMD:X})")
                resp = self.send_directly(pkt)
                if resp:
                    log(self.log, f"[Loop] ← Response: {resp.hex()}")
                else:
                    log(self.log, f"[Loop] ❌ No response received")
                time.sleep(30)  # delay 30s

        import threading
        threading.Thread(target=loop, daemon=True).start()

    def start_10x_mixed_loop(self):
        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record":  CMD_STOP_RECORD,
            "Start Place":  CMD_START_PLACE,
            "Stop Place":   CMD_STOP_PLACE,
        }
        CMD1 = cmd_options[self.cmd1_var.get()]
        CMD2 = cmd_options[self.cmd2_var.get()]
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")

        pkt1 = struct.pack("!I I H 4s 16s", CMD1, 30, 1, table, gmcode)
        pkt2 = struct.pack("!I I H 4s 16s", CMD2, 30, 1, table, gmcode)

        def loop():
            for i in range(5):
                log(self.log, f"[Mixed Loop] Round {2*i+1}/10 — sending {self.cmd1_var.get()} (0x{CMD1:X})")
                resp1 = self.send_directly(pkt1)
                time.sleep(30)

                log(self.log, f"[Mixed Loop] Round {2*i+2}/10 — sending {self.cmd2_var.get()} (0x{CMD2:X})")
                resp2 = self.send_directly(pkt2)
                time.sleep(30)

        import threading
        threading.Thread(target=loop, daemon=True).start()

    def start_gmcode_loop(self):
        async def loop_task():
            table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
            base_gmcode = self.gmcode_entry.get()

            for i in range(5):  # 5 rounds
                suffix = f"_round{i+1:02}"
                full_gmcode = (base_gmcode + suffix).encode()[:16].ljust(16, b"\0")

                pkt1 = struct.pack("!I I H 4s 16s", CMD_START_RECORD, 30, 1, table, full_gmcode)
                pkt2 = struct.pack("!I I H 4s 16s", CMD_START_PLACE, 30, 1, table, full_gmcode)
                pkt3 = struct.pack("!I I H 4s 16s", CMD_STOP_RECORD, 30, 1, table, full_gmcode)
                pkt4 = struct.pack("!I I H 4s 16s", CMD_STOP_PLACE, 30, 1, table, full_gmcode)

                log(self.log, f"[Round {i+1}/5] Sending START packets (01 03) for {base_gmcode}{suffix}")
                self.send_directly(pkt1)
                self.send_directly(pkt2)

                await asyncio.sleep(30)

                log(self.log, f"[Round {i+1}/10] Sending STOP packets (02 04) for {base_gmcode}{suffix}")
                self.send_directly(pkt3)
                self.send_directly(pkt4)

                await asyncio.sleep(30)

        import threading
        threading.Thread(target=lambda: asyncio.run(loop_task()), daemon=True).start()


    def send(self, cmd):
        log(self.log, f"[DVRRoute] Preparing to send:")
        log(self.log, f"  cmd    = 0x{cmd:X}")
        log(self.log, f"  table  = {self.table_entry.get()}")
        log(self.log, f"  gmcode = {self.gmcode_entry.get()}")

        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gmcode_entry.get().encode()[:16].ljust(16, b"\0")
        pkt = struct.pack("!I I H 4s 16s", cmd, 30, 1, table, gmcode)

        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt.hex()}")
                log(self.log, f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DVRRoute] ✅ Sent DVR cmd=0x{cmd:X}")
            except Exception as e:
                log(self.log, f"[DVRRoute] ❌ {e}")

        asyncio.get_event_loop().run_until_complete(task())

    def send_directly(self, pkt: bytes):
        try:
            log(self.log, f"[DVRRoute] (Direct) Connecting to {DVR_TARGET_IP}:{DVR_TARGET_PORT}...")
            with socket.create_connection((DVR_TARGET_IP, DVR_TARGET_PORT)) as sock:
                sock.sendall(pkt)
                resp = sock.recv(30)
                log(self.log, f"[DVRRoute] (Direct) Response from DVR : {resp.hex()}...")
                return resp
        except Exception as e:
            log(self.log, f"[DVRRoute] ❌ {e}")
            return None

class DealerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Dealer Client v20250530")

        # self.table_entry = Entry(self.root, width=8)
        # self.table_entry.insert(0, "B001")
        # self.table_entry.pack()

        # self.gm_entry = Entry(self.root, width=16)
        # self.gm_entry.insert(0, "ROUND01")
        # self.gm_entry.pack()

        # bf = tk.Frame(self.root)
        # bf.pack()
        # Button(bf, text="Start Record", command=lambda: self.send(CMD_START_RECORD)).pack(side=tk.LEFT, padx=4)
        # Button(bf, text="Stop Record", command=lambda: self.send(CMD_STOP_RECORD)).pack(side=tk.LEFT, padx=4)
        # Button(bf, text="Start Place", command=lambda: self.send(CMD_START_PLACE)).pack(side=tk.LEFT, padx=4)
        # Button(bf, text="Stop Place", command=lambda: self.send(CMD_STOP_PLACE)).pack(side=tk.LEFT, padx=4)

        Button(self.root, text="FM Manual Test", command=self.open_fm).pack(pady=3)
        Button(self.root, text="DVR Manual Test", command=self.open_dvr).pack()

        self.log = scrolledtext.ScrolledText(self.root, height=6, width=80)
        self.log.pack(pady=4)

    def send(self, cmd):
        log(self.log, f"[DealerGUI] Preparing to send:")
        log(self.log, f"  cmd    = 0x{cmd:X}")
        log(self.log, f"  table  = {self.table_entry.get()}")
        log(self.log, f"  gmcode = {self.gm_entry.get()}")

        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode = self.gm_entry.get().encode()[:16].ljust(16, b"\0")
        pkt = struct.pack("!I I H 4s 16s", cmd, 30, 1, table, gmcode)

        async def task():
            try:
                log(self.log, f"[DEBUG] Raw packet: {pkt.hex()}")
                log(self.log, f"[DealerGUI] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...")
                reader, writer = await asyncio.open_connection(MSG_HUB_IP, MSG_HUB_PORT)
                writer.write(pkt)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                log(self.log, f"[DealerGUI] ✅ Sent DVR cmd=0x{cmd:X}")
            except Exception as e:
                log(self.log, f"[DealerGUI] ❌ {e}")

        asyncio.get_event_loop().run_until_complete(task())

    def open_fm(self):
        FMRouteWindow(self.root)

    def open_dvr(self):
        DVRRouteWindow(self.root)

if __name__ == "__main__":
    DealerGUI().root.mainloop()
