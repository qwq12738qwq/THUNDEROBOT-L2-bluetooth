#!/usr/bin/env python3
"""聚焦探测：Query/Clock 变体是否有状态回传；写后等待 0.8 秒。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, hexs


async def main() -> None:
    received: list[bytes] = []

    def on_notify(sender, data: bytes) -> None:
        received.append(data)
        print(f"    <<< {hexs(data)}", flush=True)

    async with L2Controller(notify_callback=on_notify) as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display}\n")

        async def try_frame(label: str, payload: list[int]) -> None:
            if not ctl.client.is_connected:
                await ctl.connect()
            before = len(received)
            data = bytes([0x7E, *payload, 0xEF])
            print(f"[{label}] {hexs(data)}")
            try:
                await ctl.dispatch("raw", payload=payload)
                await asyncio.sleep(0.8)
                if len(received) > before:
                    print(f"  -> 收到 {len(received) - before} 条回包")
                else:
                    print("  -> 无回包")
            except Exception as exc:
                print(f"  -> 异常 {exc}")

        print("A) Query (07 EA) 第三字节变体")
        for p2 in range(0x00, 0x20):
            await try_frame(f"EA-{p2:02X}", [0x07, 0xEA, p2, 0x01, 0xFF, 0xFF, 0x00])

        print("\nB) Clock (06 83) 命令族变体")
        for p1 in range(0x80, 0xA0):
            await try_frame(f"06-{p1:02X}", [0x06, p1, 0x00, 0x00, 0x00, 0x00, 0x00])

        print("\nC) 07 05 子命令变体（白光/RGB 族）")
        for p2 in range(0x00, 0x10):
            await try_frame(f"05-{p2:02X}", [0x07, 0x05, p2, 0x00, 0x00, 0x00, 0x00])

        print(f"\n完成：回包总数 {len(received)}")


if __name__ == "__main__":
    asyncio.run(main())
