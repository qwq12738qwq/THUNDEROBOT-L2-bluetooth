#!/usr/bin/env python3
"""验证 CH=00 是否比标准 CH=05 更亮，以及它的编码行为。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, WRITE_UUID, hexs

CCT_6000K = [0x07, 0x05, 0x02, 0x00, 0x64, 0x02, 0x01]


async def main() -> None:
    async with L2Controller() as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display}\n")
        for action in ("query", "clock"):
            await ctl.dispatch(action)
            await asyncio.sleep(0.06)
        await ctl.dispatch("power", channel="front", on=True)
        await ctl.dispatch("power", channel="rear", on=True)
        await ctl.dispatch("raw", payload=CCT_6000K)
        await asyncio.sleep(0.3)
        print("前置：前后灯都开、冷白 6000K\n")

        cases = [
            ("标准前灯 CH=05", 0x05, 100, "基准亮度"),
            ("未文档 CH=00", 0x00, 100, "比基准更亮？后灯有变化吗？"),
            ("标准复查", 0x05, 100, "回到基准"),
            ("CH=00 复查", 0x00, 100, "再确认"),
            ("CH=00 LV=0", 0x00, 0, "CH=00 下 LV=0 也变暗吗？"),
            ("CH=00 LV=50", 0x00, 50, "CH=00 下亮度渐变正常吗？"),
        ]
        for label, ch, lv, note in cases:
            if not ctl.client.is_connected:
                await asyncio.sleep(0.6)
                await ctl.connect()
            await ctl.dispatch("raw", payload=CCT_6000K)
            await asyncio.sleep(0.08)
            payload = [0x04, 0x01, lv, ch, 0xFF, 0x02, 0x01]
            try:
                frames = await ctl.dispatch("raw", payload=payload)
            except Exception as exc:
                print(f"[{label}] 失败: {exc}")
                continue
            print(f"[{label}] {hexs(frames[0])}")
            print(f"  {note}")
            try:
                answer = input("  观察完按 Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break

        print("\n恢复默认")
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("power", {"channel": "rear", "on": False}),
            ("brightness", {"channel": "front", "level": 80}),
            ("cct", {"kelvin": 4500}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
