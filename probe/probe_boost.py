#!/usr/bin/env python3
"""实验性探测：亮度帧中未解释的固定字节是否藏有增益系数。

亮度帧 7E 04 01 LV CH XX YY ZZ EF
源码把 XX=FF YY=02 ZZ=01 写死但从未解释含义。
如果设备按"十进制两位"解析所有字节，FF(255)->55%，
那么 XX 改成 00(->100%) 可能解除某个折扣。
纯实验，可能闪烁/异常；每步按 Enter 观察，q 结束。
"""
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
        print("前置：前灯开、色温 6000K 冷白单路、LV=100\n")

        async def step(label: str, payload: list[int], note: str) -> bool:
            if not ctl.client.is_connected:
                await ctl.connect()
            await ctl.dispatch("raw", payload=CCT_6000K)
            await asyncio.sleep(0.08)
            frames = await ctl.dispatch("raw", payload=payload)
            print(f"[{label}] {hexs(frames[0])}")
            print(f"  {note}")
            try:
                answer = input("  观察完按 Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                return False
            return answer != "q"

        base = [0x04, 0x01, 100, 0x05, 0xFF, 0x02, 0x01]

        print("=== A组：第5字节（原 FF）— 若按两位解析 FF=55%，00=100% ===")
        for label, v, note in [
            ("基准 FF", 0xFF, "记住这个亮度"),
            ("改 00", 0x00, "更亮？更暗？一样？"),
            ("改 64", 0x64, "对比"),
            ("改 01", 0x01, "对比"),
            ("回 FF", 0xFF, "回基准确认"),
        ]:
            if not await step(label, [0x04, 0x01, 100, 0x05, v, 0x02, 0x01], note):
                break

        print("\n=== B组：第6字节（原 02）===")
        for label, v, note in [
            ("基准 02", 0x02, "记住"),
            ("改 00", 0x00, "变化？"),
            ("改 64", 0x64, "变化？"),
            ("回 02", 0x02, "回基准"),
        ]:
            if not await step(label, [0x04, 0x01, 100, 0x05, 0xFF, v, 0x01], note):
                break

        print("\n=== C组：第7字节（原 01）===")
        for label, v, note in [
            ("基准 01", 0x01, "记住"),
            ("改 00", 0x00, "变化？"),
            ("改 64", 0x64, "变化？"),
            ("回 01", 0x01, "回基准"),
        ]:
            if not await step(label, [0x04, 0x01, 100, 0x05, 0xFF, 0x02, v], note):
                break

        print("\n=== D组：连续叠加发送（测试是否累加而非覆盖）===")
        for count in (5, 20, 100):
            if not ctl.client.is_connected:
                await ctl.connect()
            await ctl.dispatch("raw", payload=CCT_6000K)
            for _ in range(count):
                await ctl.dispatch("raw", payload=base)
                await asyncio.sleep(0.055)
            print(f"连发 {count} 次 LV=100")
            try:
                answer = input("  更亮吗？Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break

        print("\n=== E组：给前灯发 RGB 帧（测试前灯是否响应 RGB）===")
        for tag, note in [(0x10, "整条纯白"), (0x20, "滚动白")]:
            if not await step(
                f"RGB tag={tag:02X}",
                [0x07, 0x05, 0x03, 0xFF, 0xFF, 0xFF, tag],
                f"前灯变白/变化？{note}",
            ):
                break

        print("\n恢复默认")
        if not ctl.client.is_connected:
            await ctl.connect()
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 80}),
            ("cct", {"kelvin": 4500}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
