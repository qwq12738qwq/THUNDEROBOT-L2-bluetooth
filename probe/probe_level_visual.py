#!/usr/bin/env python3
"""肉眼对比：LV=110 是否比 100 更亮。每步按 Enter 继续。"""
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
        await ctl.dispatch("cct", kelvin=4500)
        await asyncio.sleep(0.3)

        cases = [
            ("基准 LV=100", 100, "记住这个亮度"),
            ("目标 LV=110", 110, "比基准更亮、一样、还是变暗？"),
            ("基准复查", 100, "回到基准"),
            ("110 复查", 110, "再确认一次"),
        ]
        for label, lv, question in cases:
            payload = [0x04, 0x01, lv, 0x05, 0xFF, 0x02, 0x01]
            frames = await ctl.dispatch("raw", payload=payload)
            print(f"[{label}] LV={lv}  {hexs(frames[0])}")
            print(f"  {question}")
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
