import shutil
from pathlib import Path
import sys

# ─── Paths ─────────────────────────────────────────────
root = Path(__file__).resolve().parent
dist = root / "dist"

# ─── Shared folders to copy ────────────────────────────
shared_dirs = ["static"]
for dname in shared_dirs:
    src = root / dname
    dst = dist / dname
    if not src.exists():
        print(f"[⚠️] Warning: '{dname}/' folder not found, skipping.")
        continue
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"[✅] Copied {dname}/ → dist/{dname}/")

# ─── Copy config.env ───────────────────────────────────
config_src = root / "config.env"
config_dst = dist / "config.env"
if not config_src.exists():
    print("[❌] ERROR: config.env not found in project root.")
    sys.exit(1)

shutil.copy2(config_src, config_dst)
print("[✅] Copied config.env → dist/config.env")

# # ─── Copy HTTPS cert/key into dist/ ───────────────────
# crt_file = root / "server.crt"
# key_file = root / "server.key"

# if crt_file.exists() and key_file.exists():
#     shutil.copy2(crt_file, dist / "server.crt")
#     shutil.copy2(key_file,  dist / "server.key")
#     print("[✅] Copied server.crt and server.key → dist/")
# else:
#     print("[⚠️] Warning: server.crt/key not found, skipping HTTPS cert copy.")

# post_build.py  (at the very end)
for fname in ["generate_ssl.sh", "start_all.sh"]:                       # ✨ NEW
    src = root / fname
    dst = dist / fname
    shutil.copy2(src, dst)
    # make the shell script executable once it's in dist/
    if fname.endswith(".sh"):
        dst.chmod(0o777)

print("[✅] Added start_all.sh to dist/")
