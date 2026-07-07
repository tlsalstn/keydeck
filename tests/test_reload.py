import asyncio
import os
import shutil
import time
from pathlib import Path

import server.main as main

FIXTURE = Path(__file__).parent / "fixtures" / "mapping.yaml"


def use_tmp_config(tmp_path, monkeypatch):
    cfg = tmp_path / "mapping.yaml"
    shutil.copy(FIXTURE, cfg)
    monkeypatch.setattr(main, "CONFIG_PATH", cfg)
    main.state.config = main.load_config(cfg)
    main._reload_mtime = cfg.stat().st_mtime
    return cfg


def test_no_change_returns_none(tmp_path, monkeypatch):
    use_tmp_config(tmp_path, monkeypatch)
    assert asyncio.run(main.check_reload()) is None


def test_reload_on_change(tmp_path, monkeypatch):
    cfg = use_tmp_config(tmp_path, monkeypatch)
    text = cfg.read_text().replace('label: "재생"', 'label: "PLAY"')
    cfg.write_text(text)
    os.utime(cfg, (time.time() + 5, time.time() + 5))  # mtime 확실히 변경
    assert asyncio.run(main.check_reload()) == "reloaded"
    assert main.state.config.pages["default"]["F5"].label == "PLAY"


def test_invalid_config_keeps_old(tmp_path, monkeypatch):
    cfg = use_tmp_config(tmp_path, monkeypatch)
    old = main.state.config
    cfg.write_text("pages: [broken")
    os.utime(cfg, (time.time() + 5, time.time() + 5))
    assert asyncio.run(main.check_reload()) == "error"
    assert main.state.config is old


def test_config_file_vanishes_mid_reload(tmp_path, monkeypatch):
    """stat 이후 read 이전에 파일이 사라져도 error 반환, 예외 전파 없음."""
    cfg = use_tmp_config(tmp_path, monkeypatch)
    cfg.write_text(cfg.read_text())
    os.utime(cfg, (time.time() + 5, time.time() + 5))
    real_load = main.load_config

    def raising_load(path):
        raise FileNotFoundError(f"gone: {path}")

    monkeypatch.setattr(main, "load_config", raising_load)
    assert asyncio.run(main.check_reload()) == "error"
    monkeypatch.setattr(main, "load_config", real_load)
