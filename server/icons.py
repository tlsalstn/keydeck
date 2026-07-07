"""launch 앱의 실제 아이콘 파일 해석 — .desktop Icon= 값을 테마 아이콘 파일로 변환."""
import re
from pathlib import Path

from .actions import APP_DIRS

PIXMAPS = Path("/usr/share/pixmaps")
ICON_ROOTS = [Path.home() / ".local/share/icons", Path("/usr/share/icons")]

_cache: dict[str, Path | None] = {}


def _icon_name(app: str) -> str | None:
    for base in APP_DIRS:
        desktop = base / f"{app}.desktop"
        if desktop.exists():
            for line in desktop.read_text(errors="replace").splitlines():
                if line.startswith("Icon="):
                    return line[5:].strip()
            return None
    return None


def _size_of(path: Path) -> int:
    m = re.search(r"(\d+)x\d+", str(path))
    if m:
        return int(m.group(1))
    m = re.search(r"/(\d+)/", str(path))  # breeze 레이아웃: apps/48/name.svg
    return int(m.group(1)) if m else 0


def resolve_icon(app: str) -> Path | None:
    """앱의 아이콘 파일 경로. SVG 우선, PNG는 큰 사이즈 우선. 없으면 None."""
    if app in _cache:
        return _cache[app]
    result = None
    name = _icon_name(app)
    if name:
        p = Path(name)
        if p.is_absolute():
            result = p if p.exists() else None
        else:
            candidates: list[Path] = []
            for root in ICON_ROOTS:
                candidates += root.glob(f"*/*/apps/{name}.*")    # hicolor: theme/SIZE/apps/
                candidates += root.glob(f"*/apps/*/{name}.*")    # breeze: theme/apps/SIZE/
                candidates += root.glob(f"*/*/legacy/{name}.*")  # AdwaitaLegacy: theme/SIZE/legacy/
            for ext in ("png", "svg", "xpm"):
                pix = PIXMAPS / f"{name}.{ext}"
                if pix.exists():
                    candidates.append(pix)
            svgs = [c for c in candidates if c.suffix == ".svg"]
            pngs = sorted((c for c in candidates if c.suffix != ".svg"),
                          key=_size_of, reverse=True)
            result = (svgs or pngs or [None])[0]
    _cache[app] = result
    return result
