#!/usr/bin/env python3
"""Mac 없이 키 이벤트를 주입하는 E2E 검증 클라이언트.

사용: /usr/bin/python3 scripts/fake_client.py F5 --token test-token
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.keycodes import KVK_TO_NAME  # noqa: E402

NAME_TO_KVK = {v: k for k, v in KVK_TO_NAME.items()}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", choices=sorted(NAME_TO_KVK), metavar="KEY",
                    help="키 이름 (예: F5, A, Space)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--token", required=True)
    args = ap.parse_args()

    code = NAME_TO_KVK[args.key]
    uri = f"ws://{args.host}:{args.port}/ws/client?token={args.token}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "hello", "client": "fake", "version": 1}))
        await ws.send(json.dumps({"type": "key", "code": code, "event": "down", "repeat": False}))
        await ws.send(json.dumps({"type": "key", "code": code, "event": "up", "repeat": False}))
        print(f"sent {args.key} (kVK {code}) → {args.host}:{args.port}")


asyncio.run(main())
