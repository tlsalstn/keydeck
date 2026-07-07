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


def test_placeholder_token_rejected(tmp_path):
    with pytest.raises(ConfigError, match="token"):
        load_config(write(tmp_path, VALID.replace('token: "secret"', 'token: "CHANGE-ME-something"')))


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


def test_invalid_port_type(tmp_path):
    with pytest.raises(ConfigError, match="port"):
        load_config(write(tmp_path, VALID.replace("port: 8787", 'port: "abc"')))


def test_null_port(tmp_path):
    with pytest.raises(ConfigError, match="port"):
        load_config(write(tmp_path, VALID.replace("port: 8787", "port:")))


def test_page_bindings_not_dict(tmp_path):
    bad = """
server:
  port: 8787
  token: "secret"
pages:
  default: [1, 2, 3]
"""
    with pytest.raises(ConfigError, match="dict"):
        load_config(write(tmp_path, bad))


def test_repeat_not_boolean(tmp_path):
    with pytest.raises(ConfigError, match="repeat"):
        load_config(write(tmp_path, VALID.replace("repeat: true", 'repeat: "yes"')))


PAGED = """
server:
  port: 8787
  token: "secret"
pages:
  default:
    Tab: {label: "페이지 2", action: {type: page, to: page2}}
    F1: {label: "터미널", action: {type: launch, app: org.kde.konsole}}
  page2:
    Tab: {label: "메인", action: {type: page, to: default}}
"""


def test_page_action_valid(tmp_path):
    cfg = load_config(write(tmp_path, PAGED))
    assert cfg.pages["default"]["Tab"].action == {"type": "page", "to": "page2"}
    assert cfg.pages["page2"]["Tab"].action == {"type": "page", "to": "default"}


def test_page_action_unknown_target(tmp_path):
    with pytest.raises(ConfigError, match="존재하지 않는 페이지"):
        load_config(write(tmp_path, PAGED.replace("to: page2", "to: ghost")))


def test_page_action_missing_to(tmp_path):
    with pytest.raises(ConfigError, match="to"):
        load_config(write(tmp_path, PAGED.replace("type: page, to: page2", "type: page")))
