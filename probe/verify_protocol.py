#!/usr/bin/env python3
"""握手/查询验证：仅通过统一封装 L2Controller.dispatch() 下发。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, hexs


async def main() -> None:
    def notify(sender, data: bytes) -> None:
        print(f"  <<< NOTIFY {hexs(data)}", flush=True)

    async with L2Controller(notify_callback=notify) as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display} ({dev.address})")
        for data in await ctl.dispatch("handshake"):
            print(f">>> HANDSHAKE {hexs(data)}")
        print("等待 4 秒接收通知...")
        await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
