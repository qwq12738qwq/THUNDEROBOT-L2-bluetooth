#!/usr/bin/env python3
"""确认 0x95 命令的行为：是否稳定导致断开，参数是否影响结果。"""
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

        cases = [
            ("原始", [0x07, 0x95, 0x00, 0x00, 0x00, 0x00, 0x00]),
            ("全FF", [0x07, 0x95, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]),
            ("参数01", [0x07, 0x95, 0x01, 0x00, 0x00, 0x00, 0x00]),
        ]
        for label, payload in cases:
            if not ctl.client.is_connected:
                await ctl.connect()
            data = bytes([0x7E, *payload, 0xEF])
            print(f"发送 [{label}] {hexs(data)}")
            try:
                await ctl.dispatch("raw", payload=payload)
                await asyncio.sleep(1.0)
                alive = ctl.client.is_connected if ctl.client else False
                print(f"  结果: {'仍连接' if alive else '断开（疑似重启/复位）'}\n")
            except Exception as exc:
                print(f"  结果: 写入异常 {exc}\n")

        if not ctl.client.is_connected:
            await ctl.connect()
        print("恢复默认状态")
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
