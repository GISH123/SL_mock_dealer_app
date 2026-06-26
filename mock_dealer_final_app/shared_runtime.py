from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path


def runtime_root(anchor_file: str | Path | None = None) -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    if anchor_file is None:
        return Path.cwd()
    return Path(anchor_file).resolve().parent


def project_root(anchor_file: str | Path) -> Path:
    return Path(anchor_file).resolve().parent.parent


def resolve_env_path(anchor_file: str | Path, filename: str = '.env') -> Path:
    runtime_candidate = runtime_root(anchor_file) / filename
    if runtime_candidate.exists():
        return runtime_candidate
    local_candidate = Path(anchor_file).resolve().parent / filename
    if local_candidate.exists():
        return local_candidate
    return runtime_candidate


def resolve_sidecar_path(anchor_file: str | Path, filename: str) -> Path:
    return runtime_root(anchor_file) / filename


def resolve_card_pack_dir(anchor_file: str | Path, pack_subdir: str = 'greywyvern-cardset') -> Path:
    candidates = [
        runtime_root(anchor_file) / 'card_shown_ui' / pack_subdir,
        Path(anchor_file).resolve().parent / 'card_shown_ui' / pack_subdir,
        project_root(anchor_file) / 'card_shown_ui' / pack_subdir,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def instance_timestamp_log_path(anchor_file: str | Path, stem: str | None = None) -> Path:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'{ts}.log' if not stem else f'{stem}_{ts}.log'
    return runtime_root(anchor_file) / name


class UILogMirror:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open('a', encoding='utf-8')
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        if line is None:
            return
        text = str(line)
        if not text.endswith('\n'):
            text += '\n'
        with self._lock:
            self._fp.write(text)
            self._fp.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._fp.close()
            except Exception:
                pass
