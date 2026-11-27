#!/usr/bin/env python3
"""验证假设：亮度字节按十进制取后两位，00 代表 100%。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, hexs

CCT_6000K = [0x07, 0x05, 0x02, 0x00, 0x64, 0x02, 0x01]


async def main() -> None:
    async with L2Controller() as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display}\n")
        for action in ("query", "clock"):
            await ctl.dispatch(action)
            await asyncio.sleep(0.06)
        await ctl.dispatch("power", channel="front", on=True)
        await ctl.dispatch("raw", payload=CCT_6000K)
        await asyncio.sleep(0.3)
        print("前置：前灯开、色温固定 6000K（冷白单路）\n")

        cases = [
            ("0 → 应最亮", 0),
            ("1 → 应 1%", 1),
            ("10 → 应 10%", 10),
            ("50 → 应 50%", 50),
            ("99 → 应 99%", 99),
            ("100 → 应最亮", 100),
            ("110 → 应 10%", 110),
            ("200 → 应最亮?", 200),
            ("255 → 应 55%?", 255),
        ]
        for label, lv in cases:
            await ctl.dispatch("raw", payload=CCT_6000K)
            await asyncio.sleep(0.1)
            payload = [0x04, 0x01, lv, 0x05, 0xFF, 0x02, 0x01]
            frames = await ctl.dispatch("raw", payload=payload)
            print(f"[{label}] 字节={lv} 帧={hexs(frames[0])}")
            try:
                answer = input("  观察完按 Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break

        print("\n恢复默认")
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 80}),
            ("cct", {"kelvin": 4500}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
