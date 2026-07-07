import pytest

from server import icons


@pytest.fixture
def iconenv(tmp_path, monkeypatch):
    """가짜 .desktop + 아이콘 테마 디렉터리 환경."""
    apps = tmp_path / "applications"
    themes = tmp_path / "icons"
    pixmaps = tmp_path / "pixmaps"
    for d in (apps, themes, pixmaps):
        d.mkdir()
    monkeypatch.setattr(icons, "APP_DIRS", [apps])
    monkeypatch.setattr(icons, "ICON_ROOTS", [themes])
    monkeypatch.setattr(icons, "PIXMAPS", pixmaps)
    monkeypatch.setattr(icons, "_cache", {})
    return tmp_path


def write_desktop(env, app, icon_name):
    (env / "applications" / f"{app}.desktop").write_text(
        f"[Desktop Entry]\nName={app}\nIcon={icon_name}\n")


def test_absolute_icon_path(iconenv):
    target = iconenv / "pixmaps" / "slack.png"
    target.write_bytes(b"png")
    write_desktop(iconenv, "slack", str(target))
    assert icons.resolve_icon("slack") == target


def test_largest_png_preferred(iconenv):
    write_desktop(iconenv, "firefox", "firefox")
    for size in ("32x32", "256x256", "64x64"):
        d = iconenv / "icons" / "hicolor" / size / "apps"
        d.mkdir(parents=True)
        (d / "firefox.png").write_bytes(b"png")
    assert "256x256" in str(icons.resolve_icon("firefox"))


def test_svg_preferred_over_png(iconenv):
    write_desktop(iconenv, "ws", "ws-icon")
    png = iconenv / "icons" / "hicolor" / "512x512" / "apps"
    svg = iconenv / "icons" / "hicolor" / "scalable" / "apps"
    png.mkdir(parents=True)
    svg.mkdir(parents=True)
    (png / "ws-icon.png").write_bytes(b"png")
    (svg / "ws-icon.svg").write_bytes(b"<svg/>")
    assert icons.resolve_icon("ws").suffix == ".svg"


def test_pixmaps_fallback(iconenv):
    write_desktop(iconenv, "code", "vscode")
    (iconenv / "pixmaps" / "vscode.png").write_bytes(b"png")
    assert icons.resolve_icon("code") == iconenv / "pixmaps" / "vscode.png"


def test_breeze_layout(iconenv):
    """breeze는 theme/apps/SIZE/name.svg 역순 레이아웃."""
    write_desktop(iconenv, "konsole", "utilities-terminal")
    d = iconenv / "icons" / "breeze" / "apps" / "48"
    d.mkdir(parents=True)
    (d / "utilities-terminal.svg").write_bytes(b"<svg/>")
    assert icons.resolve_icon("konsole").suffix == ".svg"


def test_none_when_no_desktop(iconenv):
    assert icons.resolve_icon("nope") is None


def test_none_when_icon_file_missing(iconenv):
    write_desktop(iconenv, "ghost", "ghost-icon")
    assert icons.resolve_icon("ghost") is None
