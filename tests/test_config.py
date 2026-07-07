import pytest

from server.config import ConfigError, load_config

VALID = """
server:
  port: 8787
  token: "secret"
pages:
  default:
    F1: {label: "터미널", icon: "🖥️", action: {type: launch, app: org.kde.konsole}}
    F6: {label: "볼륨+", action: {type: media, op: volume-up}, repeat: true}
"""


def write(tmp_path, text):
    p = tmp_path / "mapping.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.port == 8787 and cfg.token == "secret"
    f1 = cfg.pages["default"]["F1"]
    assert f1.label == "터미널" and f1.icon == "🖥️" and f1.repeat is False
    assert f1.action == {"type": "launch", "app": "org.kde.konsole"}
    assert cfg.pages["default"]["F6"].repeat is True
    assert cfg.pages["default"]["F6"].icon is None


def test_missing_token(tmp_path):
    with pytest.raises(ConfigError, match="token"):
        load_config(write(tmp_path, VALID.replace('token: "secret"', "")))


def test_missing_default_page(tmp_path):
    with pytest.raises(ConfigError, match="default"):
        load_config(write(tmp_path, VALID.replace("default:", "other:")))


def test_unknown_key_name(tmp_path):
    with pytest.raises(ConfigError, match="키 이름"):
        load_config(write(tmp_path, VALID.replace("F6:", "SuperKey:")))


def test_unknown_action_type(tmp_path):
    with pytest.raises(ConfigError, match="액션 타입"):
        load_config(write(tmp_path, VALID.replace("type: media, op: volume-up", "type: warp")))


def test_missing_required_action_field(tmp_path):
    with pytest.raises(ConfigError, match="cmd"):
        load_config(write(tmp_path, VALID.replace(
            "action: {type: media, op: volume-up}", "action: {type: shell}")))


def test_broken_yaml(tmp_path):
    with pytest.raises(ConfigError, match="YAML"):
        load_config(write(tmp_path, "pages: [unclosed"))
