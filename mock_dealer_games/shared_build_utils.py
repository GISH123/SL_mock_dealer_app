from __future__ import annotations

import shutil
from pathlib import Path


def bump_version(version_file: str | Path, default: str = 'v1_0_0') -> str:
    path = Path(version_file)
    if not path.exists():
        path.write_text(default, encoding='utf-8')
    raw = path.read_text(encoding='utf-8').strip().replace('v', '')
    try:
        major, minor, patch = map(int, raw.split('_'))
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    if patch >= 100:
        patch = 0
        minor += 1
    if minor >= 100:
        minor = 0
        major += 1
    new_version = f'v{major}_{minor}_{patch}'
    path.write_text(new_version, encoding='utf-8')
    return new_version


def copy_card_shown_ui(project_root: str | Path, dist_dir: str | Path) -> bool:
    project_root = Path(project_root)
    dist_dir = Path(dist_dir)
    src = project_root / 'card_shown_ui'
    dst = dist_dir / 'card_shown_ui'
    if not src.exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True
