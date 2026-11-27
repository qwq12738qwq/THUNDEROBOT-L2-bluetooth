#!/usr/bin/env python3
"""实验：WW+CW 越界值（60+60、100+100）是否被设备接受。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, WRITE_UUID, hexs


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
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 100}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)
        print("前置：前灯开、亮度 100\n")

        cases = [
            ("基准 3000K", 100, 0),
            ("基准 4500K", 50, 50),
            ("基准 6000K", 0, 100),
            ("实验 60+60", 60, 60),
            ("实验 100+100", 100, 100),
            ("对比 60+40", 60, 40),
        ]

        for label, ww, cw in cases:
            if not ctl.client.is_connected:
                print("设备断开，重连中...")
                await ctl.connect()
            payload = [0x07, 0x05, 0x02, ww, cw, 0x02, 0x01]
            frame = bytes([0x7E, *payload, 0xEF])
            before = len(received)
            print(f"[{label}] WW={ww} CW={cw} 总和={ww + cw}")
            print(f"  帧 {hexs(frame)}")
            try:
                await ctl.dispatch("raw", payload=payload)
                await asyncio.sleep(1.2)
                alive = ctl.client.is_connected if ctl.client else False
                got = len(received) - before
                print(f"  连接: {'正常' if alive else '断开'}  通知: {got} 条")
                try:
                    val = await ctl.client.read_gatt_char(WRITE_UUID)
                    print(f"  FFF3 回读: {hexs(val)}")
                except Exception as exc:
                    print(f"  FFF3 回读失败: {exc}")
            except Exception as exc:
                print(f"  写入异常: {exc}")
            print()

        print("恢复默认状态")
        if not ctl.client.is_connected:
            await ctl.connect()
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 80}),
            ("cct", {"kelvin": 4500}),
        ]:
            for f in await ctl.dispatch(action, **params):
                print(f"  {action}: {hexs(f)}")
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
