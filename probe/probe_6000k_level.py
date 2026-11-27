#!/usr/bin/env python3
"""6000K 极端色温下测试亮度 100/110/120，排除混光干扰。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, WRITE_UUID, hexs

CCT_6000K = [0x07, 0x05, 0x02, 0x00, 0x64, 0x02, 0x01]


async def main() -> None:
    received: list[bytes] = []

    def on_notify(sender, data: bytes) -> None:
        received.append(data)
        print(f"    <<< 通知 {hexs(data)}", flush=True)

    async with L2Controller(notify_callback=on_notify) as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display} ({dev.address})\n")
        for action in ("query", "clock"):
            await ctl.dispatch(action)
            await asyncio.sleep(0.06)
        await ctl.dispatch("power", channel="front", on=True)
        await ctl.dispatch("raw", payload=CCT_6000K)
        await asyncio.sleep(0.3)
        print("前置：前灯开、色温固定 6000K（WW=0 CW=100）\n")

        cases = [
            ("基准 100%", 100),
            ("测试 110%", 110),
            ("测试 120%", 120),
            ("回基准 100%", 100),
        ]

        for label, lv in cases:
            if not ctl.client.is_connected:
                print("设备断开，重连中...")
                await ctl.connect()
            await ctl.dispatch("raw", payload=CCT_6000K)
            await asyncio.sleep(0.1)
            payload = [0x04, 0x01, lv, 0x05, 0xFF, 0x02, 0x01]
            frame = bytes([0x7E, *payload, 0xEF])
            before = len(received)
            print(f"[{label}] LV={lv}  {hexs(frame)}")
            try:
                await ctl.dispatch("raw", payload=payload)
                await asyncio.sleep(1.0)
                alive = ctl.client.is_connected if ctl.client else False
                got = len(received) - before
                print(f"  连接: {'正常' if alive else '断开'}  通知: {got} 条")
                try:
                    val = await ctl.client.read_gatt_char(WRITE_UUID)
                    print(f"  FFF3: {hexs(val[:8])}...")
                except Exception as exc:
                    print(f"  FFF3 读失败: {exc}")
            except Exception as exc:
                print(f"  写入失败: {exc}")
            print()

        print("恢复默认")
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
