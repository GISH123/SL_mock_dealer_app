import datetime
import httpx
import tkinter as tk
from tkinter import ttk, messagebox

BRIDGE_PORT  = 8080

class ManualPanel:
    def __init__(self):
        self.root = tk.Tk(); self.root.title("DVR bridge tester(this app only http/https post to the indicated IP)")
        ttk.Label(self.root, text="Bridge URL").grid(row=0, column=0, padx=5, pady=5)
        self.url = tk.StringVar(value=f"http://127.0.0.1:{BRIDGE_PORT}")
        ttk.Entry(self.root, textvariable=self.url, width=30).grid(row=0, column=1, padx=5, pady=5)

        row = 1
        for text, ep in [("Start Record", "/record/start"),
                         ("Stop Record",  "/record/stop"),
                         ("Start Place",  "/place/start"),
                         ("Stop Place",   "/place/stop")]:
            ttk.Button(self.root, text=text,
                       command=lambda e=ep,t=text:self._fire(e,t)).grid(row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
            row += 1

        ttk.Button(self.root, text="Quit", command=self.root.destroy).grid(row=row, column=0, columnspan=2, pady=6)

    def _fire(self, ep, label):
        base = self.url.get().rstrip("/")
        gm   = datetime.datetime.now().strftime("BJ%Y%m%d_%H%M%S")
        try:
            r = httpx.post(f"{base}{ep}",
                           json={"table": "T032", "gmcode": gm},
                           timeout=5, verify=False)
            ok = r.json()["ret_code"] == 0
            messagebox.showinfo(label, f"{label} ⇒ {'OK' if ok else 'ERROR'}")
        except Exception as e:
            messagebox.showerror(label, f"Request failed:\n{e}")

    def run(self): self.root.mainloop()

def main():
    ManualPanel().run()

if __name__ == "__main__":
    main()
