from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

CONFIG_SRC = ROOT / "config.env"
CONFIG_DST = DIST / "config.env"

STATIC_SRC = ROOT / "static"

GATEWAY_DIRS = [
    "dvr_gateway_http_exec",
    "dvr_gateway_https_exec",
    "fm_gateway_exec",
    "fm_gateway_https_exec",
]

LAUNCHER_FILES = [
    "generate_ssl.sh",
    "start_all_linux.sh",
    "start_all_windows.bat",
]


def fail(message: str) -> None:
    print(f"[ERROR] {message}")
    sys.exit(1)


def copy_file(src: Path, dst: Path, required: bool = True) -> None:
    if not src.exists():
        if required:
            fail(f"Required file not found: {src}")
        print(f"[WARN] Optional file not found, skipping: {src}")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[OK] Copied {src.name} -> {dst}")


def copy_tree(src: Path, dst: Path, required: bool = True) -> None:
    if not src.exists():
        if required:
            fail(f"Required folder not found: {src}")
        print(f"[WARN] Optional folder not found, skipping: {src}")
        return

    if dst.exists():
        shutil.rmtree(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    print(f"[OK] Copied folder {src} -> {dst}")


def find_openssl() -> Path | None:
    candidates = [
        shutil.which("openssl"),
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files\Git\mingw64\bin\openssl.exe",
    ]

    for item in candidates:
        if item and Path(item).exists():
            return Path(item)

    return None


def ensure_ca_cert() -> None:
    ca_dir = DIST / "CA"
    crt_dst = ca_dir / "server.crt"
    key_dst = ca_dir / "server.key"

    if crt_dst.exists() and key_dst.exists():
        print(f"[OK] Existing HTTPS cert found: {ca_dir}")
        return

    root_ca_dir = ROOT / "CA"
    root_crt = root_ca_dir / "server.crt"
    root_key = root_ca_dir / "server.key"

    if root_crt.exists() and root_key.exists():
        ca_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root_crt, crt_dst)
        shutil.copy2(root_key, key_dst)
        print(f"[OK] Copied HTTPS certs from {root_ca_dir} -> {ca_dir}")
        return

    root_crt_alt = ROOT / "server.crt"
    root_key_alt = ROOT / "server.key"

    if root_crt_alt.exists() and root_key_alt.exists():
        ca_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root_crt_alt, crt_dst)
        shutil.copy2(root_key_alt, key_dst)
        print(f"[OK] Copied HTTPS certs from project root -> {ca_dir}")
        return

    openssl = find_openssl()
    if not openssl:
        fail(
            "HTTPS certs are missing and OpenSSL was not found. "
            "Install Git for Windows or provide CA/server.crt and CA/server.key."
        )

    ca_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(openssl),
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(key_dst),
        "-out",
        str(crt_dst),
        "-days",
        "3650",
        "-subj",
        "/C=TW/ST=Taiwan/L=Taipei/O=SL/OU=Dev/CN=localhost",
    ]

    print(f"[INFO] Generating HTTPS certs with OpenSSL: {openssl}")
    subprocess.run(cmd, check=True)

    if not crt_dst.exists() or not key_dst.exists():
        fail("OpenSSL command completed but server.crt/server.key were not created.")

    print(f"[OK] Generated HTTPS certs -> {ca_dir}")


def copy_static_assets() -> None:
    copy_tree(STATIC_SRC, DIST / "static", required=True)

    for folder in GATEWAY_DIRS:
        service_dir = DIST / folder
        if not service_dir.exists():
            print(f"[WARN] Gateway folder not found, skipping static copy: {service_dir}")
            continue

        copy_tree(STATIC_SRC, service_dir / "static", required=True)


def copy_launchers() -> None:
    for fname in LAUNCHER_FILES:
        src = ROOT / fname
        dst = DIST / fname
        copy_file(src, dst, required=True)

        if fname.endswith(".sh"):
            try:
                dst.chmod(0o777)
            except Exception as exc:
                print(f"[WARN] Could not chmod {dst}: {exc}")


def main() -> None:
    if not DIST.exists():
        fail(f"dist folder not found: {DIST}")

    copy_file(CONFIG_SRC, CONFIG_DST, required=True)
    copy_static_assets()
    ensure_ca_cert()
    copy_launchers()

    print("")
    print("[OK] Post-build packaging completed.")
    print("[OK] Remote should now be able to run: dist/start_all_windows.bat")


if __name__ == "__main__":
    main()