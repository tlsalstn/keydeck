"""mapping.yaml 로드·검증. 실패 시 ConfigError — 호출측이 이전 설정을 유지한다."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .actions import EXECUTORS, REQUIRED_FIELDS
from .keycodes import KVK_TO_NAME

VALID_KEY_NAMES = set(KVK_TO_NAME.values())


class ConfigError(Exception):
    pass


@dataclass
class Binding:
    key: str
    label: str
    action: dict
    icon: str | None = None
    repeat: bool = False


@dataclass
class Config:
    port: int
    token: str
    pages: dict[str, dict[str, Binding]]


def load_config(path: Path) -> Config:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML 파싱 실패: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("최상위는 매핑(dict)이어야 합니다")

    server = raw.get("server") or {}
    token = server.get("token")
    if not token or not isinstance(token, str):
        raise ConfigError("server.token 필수 (문자열)")
    port = int(server.get("port", 8787))

    pages_raw = raw.get("pages")
    if not isinstance(pages_raw, dict) or "default" not in pages_raw:
        raise ConfigError("pages.default 필수")

    pages: dict[str, dict[str, Binding]] = {}
    for page_name, keys in pages_raw.items():
        page: dict[str, Binding] = {}
        for key, spec in (keys or {}).items():
            if key not in VALID_KEY_NAMES:
                raise ConfigError(f"알 수 없는 키 이름: {key} (예: F1, A, Digit1, Space)")
            if not isinstance(spec, dict) or "label" not in spec or "action" not in spec:
                raise ConfigError(f"{key}: label과 action 필수")
            action = spec["action"]
            atype = action.get("type") if isinstance(action, dict) else None
            if atype not in EXECUTORS:
                raise ConfigError(
                    f"{key}: 알 수 없는 액션 타입 {atype!r} (지원: {', '.join(sorted(EXECUTORS))})")
            missing = [f for f in REQUIRED_FIELDS[atype] if f not in action]
            if missing:
                raise ConfigError(f"{key}: {atype} 액션에 필수 필드 누락: {', '.join(missing)}")
            page[key] = Binding(
                key=key,
                label=str(spec["label"]),
                action=action,
                icon=spec.get("icon"),
                repeat=bool(spec.get("repeat", False)),
            )
        pages[page_name] = page
    return Config(port=port, token=token, pages=pages)
