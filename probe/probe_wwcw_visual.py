#!/usr/bin/env python3
"""肉眼对比：越界 WW+CW 是否让灯更亮。每步按 Enter 继续。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, hexs


async def main() -> None:
    async with L2Controller() as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display}\n")
        for action in ("query", "clock"):
            await ctl.dispatch(action)
            await asyncio.sleep(0.06)
        await ctl.dispatch("power", channel="front", on=True)
        await ctl.dispatch("brightness", channel="front", level=100)
        await asyncio.sleep(0.3)

        cases = [
            ("基准 A", 50, 50, "记住这个亮度和颜色"),
            ("越界 60+60", 60, 60, "比基准 A 更亮吗？颜色变了吗？"),
            ("越界 100+100", 100, 100, "比 60+60 还亮吗？"),
            ("基准 B", 50, 50, "回到基准，确认差异是否可重复"),
            ("越界 60+60", 60, 60, "再看一次，是否稳定更亮"),
        ]
        for label, ww, cw, question in cases:
            payload = [0x07, 0x05, 0x02, ww, cw, 0x02, 0x01]
            frames = await ctl.dispatch("raw", payload=payload)
            print(f"[{label}] WW={ww} CW={cw} 总和={ww + cw}  {hexs(frames[0])}")
            print(f"  {question}")
            try:
                answer = input("  观察完按 Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break

        print("\n恢复默认状态")
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 80}),
            ("cct", {"kelvin": 4500}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
