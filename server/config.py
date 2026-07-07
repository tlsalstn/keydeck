"""mapping.yaml 로드·검증. 실패 시 ConfigError — 호출측이 이전 설정을 유지한다."""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .actions import EXECUTORS, REQUIRED_FIELDS
from .keycodes import KVK_TO_NAME

VALID_KEY_NAMES = set(KVK_TO_NAME.values())

# 서버 상태를 바꾸는 액션 — 호스트 실행기(EXECUTORS)가 아니라 main의 디스패치가 처리
SERVER_ACTION_FIELDS = {"page": ["to"]}


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
    if token.startswith("CHANGE-ME"):
        raise ConfigError("server.token이 예시 그대로입니다 — 실제 토큰을 생성해 넣으세요 "
                          "(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')")
    try:
        port = int(server.get("port", 8787))
    except (TypeError, ValueError) as e:
        raise ConfigError(f"server.port는 정수여야 합니다: {server.get('port')!r}") from e

    pages_raw = raw.get("pages")
    if not isinstance(pages_raw, dict) or "default" not in pages_raw:
        raise ConfigError("pages.default 필수")

    pages: dict[str, dict[str, Binding]] = {}
    for page_name, keys in pages_raw.items():
        page: dict[str, Binding] = {}
        if keys is None:
            keys = {}
        if not isinstance(keys, dict):
            raise ConfigError(f"페이지 {page_name}의 키 매핑은 dict여야 합니다")
        for key, spec in keys.items():
            if key not in VALID_KEY_NAMES:
                raise ConfigError(f"알 수 없는 키 이름: {key} (예: F1, A, Digit1, Space)")
            if not isinstance(spec, dict) or "label" not in spec or "action" not in spec:
                raise ConfigError(f"{key}: label과 action 필수")
            action = spec["action"]
            atype = action.get("type") if isinstance(action, dict) else None
            if atype not in EXECUTORS and atype not in SERVER_ACTION_FIELDS:
                valid = sorted(set(EXECUTORS) | set(SERVER_ACTION_FIELDS))
                raise ConfigError(
                    f"{key}: 알 수 없는 액션 타입 {atype!r} (지원: {', '.join(valid)})")
            required = REQUIRED_FIELDS.get(atype) or SERVER_ACTION_FIELDS[atype]
            missing = [f for f in required if f not in action]
            if missing:
                raise ConfigError(f"{key}: {atype} 액션에 필수 필드 누락: {', '.join(missing)}")
            if atype == "page" and action["to"] not in pages_raw:
                raise ConfigError(f"{key}: 존재하지 않는 페이지로 이동: {action['to']!r}")
            repeat = spec.get("repeat", False)
            if not isinstance(repeat, bool):
                raise ConfigError(f"{key}: repeat는 true/false여야 합니다")
            page[key] = Binding(
                key=key,
                label=str(spec["label"]),
                action=action,
                icon=spec.get("icon"),
                repeat=repeat,
            )
        pages[page_name] = page
    return Config(port=port, token=token, pages=pages)
