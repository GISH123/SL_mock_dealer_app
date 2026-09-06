import os
import asyncio
import struct
import tkinter as tk
import socket
import time
import threading

from datetime import datetime
from tkinter import Button, Entry, Label, scrolledtext, ttk

# ---------------------------------------------------------------------------
# This page intentionally restores the historical dealer_gui DVRRouteWindow UI.
# Keep the visible controls/layout aligned with:
#   mock_dealer_games/dealer_gui/main.py
#
# Compatibility:
# - Historical env names are preferred when present.
# - Current dealer_BAC env names DVR_IP / DVR_PORT are accepted as fallback.
# ---------------------------------------------------------------------------

MSG_HUB_IP = os.getenv(
    "MSG_HUB_SERVICE_IP",
    os.getenv("DVR_IP", "127.0.0.1"),
)
MSG_HUB_PORT = int(
    os.getenv(
        "MSG_HUB_SERVICE_PORT",
        os.getenv("DVR_PORT", "11007"),
    )
)

DVR_TARGET_IP = os.getenv(
    "DVR_TARGET_IP",
    os.getenv("DVR_IP", "127.0.0.1"),
)
DVR_TARGET_PORT = int(
    os.getenv(
        "DVR_TARGET_PORT",
        os.getenv("DVR_PORT", "11007"),
    )
)

CMD_START_RECORD = 0x20001
CMD_STOP_RECORD = 0x20002
CMD_START_PLACE = 0x20003
CMD_STOP_PLACE = 0x20004

PACKET_SIZE = 30
VERSION = 1
_PACKET_FMT = "!IIH4s16s"


def _log(widget, msg):
    widget.insert(tk.END, f"[{datetime.now().isoformat()}] {msg}\n")
    widget.see(tk.END)


# Compatibility helpers retained so the previous local test file still works
# if the earlier apply script had already been run.
COMMANDS = {
    "Start Record": CMD_START_RECORD,
    "Stop Record": CMD_STOP_RECORD,
    "Start Place": CMD_START_PLACE,
    "Stop Place": CMD_STOP_PLACE,
}


def build_request_packet(cmd: int, table: str, gmcode: str) -> bytes:
    table_b = (table or "").encode("ascii", "ignore")[:4].ljust(4, b"\x00")
    gmcode_b = (gmcode or "").encode("ascii", "ignore")[:16].ljust(16, b"\x00")
    return struct.pack(_PACKET_FMT, int(cmd), PACKET_SIZE, VERSION, table_b, gmcode_b)


def parse_request_packet(packet: bytes) -> dict:
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"expected {PACKET_SIZE} bytes, got {len(packet)}")
    cmd, size, version, table_b, gmcode_b = struct.unpack(_PACKET_FMT, packet)
    return {
        "cmd": cmd,
        "size": size,
        "version": version,
        "table": table_b.rstrip(b"\x00").decode("ascii", "replace"),
        "gmcode": gmcode_b.rstrip(b"\x00").decode("ascii", "replace"),
    }


class DVRDoublePacketTestUI:
    # Historical DVR Manual Control page from mock_dealer_games/dealer_gui/main.py.
    # The visible page is intentionally kept the same as the old DVRRouteWindow.

    def __init__(self, root, *, default_ip=None, default_port=None):
        global MSG_HUB_IP, MSG_HUB_PORT, DVR_TARGET_IP, DVR_TARGET_PORT

        # main.py loads config.env after importing this module. Resolve the
        # runtime targets here (after dotenv has been loaded), not only at
        # module import time.
        fallback_ip = str(default_ip or os.getenv("DVR_IP", "127.0.0.1"))
        fallback_port = int(default_port or os.getenv("DVR_PORT", "11007"))

        MSG_HUB_IP = os.getenv("MSG_HUB_SERVICE_IP", fallback_ip)
        MSG_HUB_PORT = int(
            os.getenv("MSG_HUB_SERVICE_PORT", str(fallback_port))
        )
        DVR_TARGET_IP = os.getenv("DVR_TARGET_IP", fallback_ip)
        DVR_TARGET_PORT = int(
            os.getenv("DVR_TARGET_PORT", str(fallback_port))
        )

        self.root = root
        self.root.title("DVR Manual Control")

        Label(self.root, text="Table").pack()
        self.table_entry = Entry(self.root, width=8)
        self.table_entry.insert(0, "T032")
        self.table_entry.pack()

        Label(self.root, text="Gmcode").pack()
        self.gmcode_entry = Entry(self.root, width=16)
        self.gmcode_entry.insert(0, "testg001")
        self.gmcode_entry.pack()

        # Historical Start Record row
        f_start = tk.Frame(self.root)
        f_start.pack(fill="x", padx=10, pady=3)
        Button(
            f_start,
            text="Start Record",
            command=lambda: self.send(CMD_START_RECORD),
        ).pack(side="left", expand=True, fill="x")
        Button(
            f_start,
            text="▶ Start Both",
            command=self.send_start_both,
        ).pack(side="left", padx=6)

        # Historical Stop Record
        Button(
            self.root,
            text="Stop Record",
            command=lambda: self.send(CMD_STOP_RECORD),
        ).pack(fill="x", padx=10, pady=3)

        # Historical Start Place
        Button(
            self.root,
            text="Start Place",
            command=lambda: self.send(CMD_START_PLACE),
        ).pack(fill="x", padx=10, pady=3)

        # Historical Stop Place row
        f_stop = tk.Frame(self.root)
        f_stop.pack(fill="x", padx=10, pady=3)
        Button(
            f_stop,
            text="Stop Place",
            command=lambda: self.send(CMD_STOP_PLACE),
        ).pack(side="left", expand=True, fill="x")
        Button(
            f_stop,
            text="■ Stop Both",
            command=self.send_stop_both,
        ).pack(side="left", padx=6)

        self.log = scrolledtext.ScrolledText(self.root, height=6, width=80)
        self.log.pack()

        # Historical custom double-packet section
        f_custom = tk.LabelFrame(
            self.root,
            text="Custom Double Packet → DVR Direct",
            padx=10,
            pady=5,
        )
        f_custom.pack(fill="x", padx=10, pady=5)

        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record": CMD_STOP_RECORD,
            "Start Place": CMD_START_PLACE,
            "Stop Place": CMD_STOP_PLACE,
        }

        Label(f_custom, text="Command 1").grid(row=0, column=0, padx=5, pady=3)
        self.cmd1_var = tk.StringVar(value="Start Record")
        cmd1_menu = ttk.Combobox(
            f_custom,
            textvariable=self.cmd1_var,
            values=list(cmd_options.keys()),
            state="readonly",
        )
        cmd1_menu.grid(row=0, column=1, padx=5)

        Label(f_custom, text="Command 2").grid(row=1, column=0, padx=5, pady=3)
        self.cmd2_var = tk.StringVar(value="Start Place")
        cmd2_menu = ttk.Combobox(
            f_custom,
            textvariable=self.cmd2_var,
            values=list(cmd_options.keys()),
            state="readonly",
        )
        cmd2_menu.grid(row=1, column=1, padx=5)

        Button(
            f_custom,
            text="Send Custom Double",
            command=lambda: self.send_double_custom(cmd_options),
        ).grid(row=0, column=2, rowspan=2, padx=10, pady=3)

        Button(
            f_custom,
            text="▶ Start 10x Loop Test (Command 1)",
            command=self.start_10x_loop,
        ).grid(row=2, column=0, columnspan=2, pady=4)

        Button(
            f_custom,
            text="▶ Start 10x Mixed Test (Command 1 then Command 2)",
            command=self.start_10x_mixed_loop,
        ).grid(row=2, column=2, pady=4)

        # Historical gmcode loop section
        f_loop_gmcode = tk.LabelFrame(
            self.root,
            text="Loop Gmcode test, four command",
            padx=10,
            pady=5,
        )
        f_loop_gmcode.pack(fill="x", padx=10, pady=5)

        Button(
            f_loop_gmcode,
            text="▶ Start Full 5-Round Game Loop",
            command=self.start_gmcode_loop,
        ).pack(pady=3)

    def _packet(self, cmd, gmcode=None):
        table = self.table_entry.get().encode()[:4].ljust(4, b"\0")
        gmcode_text = self.gmcode_entry.get() if gmcode is None else gmcode
        gmcode_b = gmcode_text.encode()[:16].ljust(16, b"\0")
        return struct.pack("!I I H 4s 16s", cmd, 30, 1, table, gmcode_b)

    def _send_to_message_hub(self, pkt, cmd):
        async def task():
            try:
                _log(self.log, f"[DEBUG] Raw packet: {pkt.hex()}")
                _log(
                    self.log,
                    f"[DVRRoute] Connecting to {MSG_HUB_IP}:{MSG_HUB_PORT}...",
                )
                reader, writer = await asyncio.open_connection(
                    MSG_HUB_IP,
                    MSG_HUB_PORT,
                )
                writer.write(pkt)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                _log(
                    self.log,
                    f"[DVRRoute] ✅ Sent DVR cmd=0x{cmd:X}",
                )
            except Exception as e:
                _log(self.log, f"[DVRRoute] ❌ {e}")

        loop = asyncio.get_event_loop()
        loop.run_until_complete(task())

    def send_start_both(self):
        pkt_start_record = self._packet(CMD_START_RECORD)
        pkt_start_place = self._packet(CMD_START_PLACE)

        self._send_to_message_hub(pkt_start_record, CMD_START_RECORD)
        self._send_to_message_hub(pkt_start_place, CMD_START_PLACE)

    def send_stop_both(self):
        pkt_stop_record = self._packet(CMD_STOP_RECORD)
        pkt_stop_place = self._packet(CMD_STOP_PLACE)

        self._send_to_message_hub(pkt_stop_record, CMD_STOP_RECORD)
        self._send_to_message_hub(pkt_stop_place, CMD_STOP_PLACE)

    def send_double_record(self, CMD1, CMD2):
        pkt1 = self._packet(CMD1)
        pkt2 = self._packet(CMD2)
        double_pkt = pkt1 + pkt2  # 60 bytes

        _log(
            self.log,
            f"[DVRRoute] Sending 2x DVR packets "
            f"(cmd=0x{CMD1:X}, 0x{CMD2:X}) via socket.sendall()",
        )
        _log(self.log, f"[DEBUG] 60-byte hex = {double_pkt.hex()}")

        try:
            resp = self.send_directly(double_pkt)
            if resp:
                _log(self.log, f"[DVR → DIRECT] ← Response: {resp.hex()}")
            else:
                _log(self.log, "[DVR → DIRECT] ❌ No response received")
        except Exception as e:
            _log(self.log, f"[DVRRoute] ❌ {e}")

    def send_double_custom(self, cmd_options):
        name1 = self.cmd1_var.get()
        name2 = self.cmd2_var.get()
        CMD1 = cmd_options[name1]
        CMD2 = cmd_options[name2]

        pkt1 = self._packet(CMD1)
        pkt2 = self._packet(CMD2)
        double_pkt = pkt1 + pkt2

        _log(
            self.log,
            f"[DVR → DIRECT] Sending to {DVR_TARGET_IP}:{DVR_TARGET_PORT}",
        )
        _log(
            self.log,
            f"[DVR → DIRECT] Sending 2x packets "
            f"(0x{CMD1:X}, 0x{CMD2:X})",
        )
        _log(self.log, f"[DEBUG] 60-byte hex = {double_pkt.hex()}")

        try:
            resp = self.send_directly(double_pkt)
            if resp:
                _log(self.log, f"[DVR → DIRECT] ← Response: {resp.hex()}")
            else:
                _log(self.log, "[DVR → DIRECT] ❌ No response received")
        except Exception as e:
            _log(self.log, f"[DVR → DIRECT] ❌ {e}")

    def start_10x_loop(self):
        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record": CMD_STOP_RECORD,
            "Start Place": CMD_START_PLACE,
            "Stop Place": CMD_STOP_PLACE,
        }
        CMD = cmd_options[self.cmd1_var.get()]
        pkt = self._packet(CMD)

        def loop():
            for i in range(10):
                _log(
                    self.log,
                    f"[Loop] Round {i+1}/10 — sending "
                    f"{self.cmd1_var.get()} (0x{CMD:X})",
                )
                resp = self.send_directly(pkt)
                if resp:
                    _log(self.log, f"[Loop] ← Response: {resp.hex()}")
                else:
                    _log(self.log, "[Loop] ❌ No response received")
                time.sleep(30)

        threading.Thread(target=loop, daemon=True).start()

    def start_10x_mixed_loop(self):
        cmd_options = {
            "Start Record": CMD_START_RECORD,
            "Stop Record": CMD_STOP_RECORD,
            "Start Place": CMD_START_PLACE,
            "Stop Place": CMD_STOP_PLACE,
        }
        CMD1 = cmd_options[self.cmd1_var.get()]
        CMD2 = cmd_options[self.cmd2_var.get()]

        pkt1 = self._packet(CMD1)
        pkt2 = self._packet(CMD2)

        def loop():
            for i in range(5):
                _log(
                    self.log,
                    f"[Mixed Loop] Round {2*i+1}/10 — sending "
                    f"{self.cmd1_var.get()} (0x{CMD1:X})",
                )
                self.send_directly(pkt1)
                time.sleep(30)

                _log(
                    self.log,
                    f"[Mixed Loop] Round {2*i+2}/10 — sending "
                    f"{self.cmd2_var.get()} (0x{CMD2:X})",
                )
                self.send_directly(pkt2)
                time.sleep(30)

        threading.Thread(target=loop, daemon=True).start()

    def start_gmcode_loop(self):
        async def loop_task():
            base_gmcode = self.gmcode_entry.get()

            for i in range(5):
                suffix = f"_round{i+1:02}"
                gmcode = (base_gmcode + suffix)[:16]

                pkt1 = self._packet(CMD_START_RECORD, gmcode)
                pkt2 = self._packet(CMD_START_PLACE, gmcode)
                pkt3 = self._packet(CMD_STOP_RECORD, gmcode)
                pkt4 = self._packet(CMD_STOP_PLACE, gmcode)

                _log(
                    self.log,
                    f"[Round {i+1}/5] Sending START packets (01 03) "
                    f"for {base_gmcode}{suffix}",
                )
                self.send_directly(pkt1)
                self.send_directly(pkt2)

                await asyncio.sleep(30)

                _log(
                    self.log,
                    f"[Round {i+1}/10] Sending STOP packets (02 04) "
                    f"for {base_gmcode}{suffix}",
                )
                self.send_directly(pkt3)
                self.send_directly(pkt4)

                await asyncio.sleep(30)

        threading.Thread(
            target=lambda: asyncio.run(loop_task()),
            daemon=True,
        ).start()

    def send(self, cmd):
        _log(self.log, "[DVRRoute] Preparing to send:")
        _log(self.log, f"  cmd    = 0x{cmd:X}")
        _log(self.log, f"  table  = {self.table_entry.get()}")
        _log(self.log, f"  gmcode = {self.gmcode_entry.get()}")

        pkt = self._packet(cmd)
        self._send_to_message_hub(pkt, cmd)

    def send_directly(self, pkt: bytes):
        try:
            _log(
                self.log,
                f"[DVRRoute] (Direct) Connecting to "
                f"{DVR_TARGET_IP}:{DVR_TARGET_PORT}...",
            )
            with socket.create_connection(
                (DVR_TARGET_IP, DVR_TARGET_PORT)
            ) as sock:
                sock.sendall(pkt)
                resp = sock.recv(30)
                _log(
                    self.log,
                    f"[DVRRoute] (Direct) Response from DVR : "
                    f"{resp.hex()}...",
                )
                return resp
        except Exception as e:
            _log(self.log, f"[DVRRoute] ❌ {e}")
            return None
