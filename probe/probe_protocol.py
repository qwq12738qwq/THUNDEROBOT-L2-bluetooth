#!/usr/bin/env python3
"""协议探测：逐帧扫描并记录导致断开/通知的帧，断开后自动重连继续。"""
from __future__ import annotations

import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l2_core import L2Controller, hexs


async def main() -> None:
    notifications: list[bytes] = []
    kills: list[tuple[str, list[int]]] = []

    def on_notify(sender, data: bytes) -> None:
        notifications.append(data)
        print(f"    <<< 通知 {hexs(data)}", flush=True)

    async with L2Controller(notify_callback=on_notify) as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display} ({dev.address})\n")

        async def send(label: str, payload: list[int]) -> None:
            before = len(notifications)
            try:
                frames = await ctl.dispatch("raw", payload=payload)
                await asyncio.sleep(0.05)
                if len(notifications) > before:
                    print(f"  [{label}] {hexs(frames[0])} -> 有通知", flush=True)
                if not ctl.client.is_connected:
                    kills.append((label, payload))
                    print(f"  [{label}] {hexs(frames[0])} -> 设备断开", flush=True)
                    await asyncio.sleep(0.5)
                    await ctl.connect()
                    print(f"  (已重连 {ctl.device.address})", flush=True)
            except Exception as exc:
                print(f"  [{label}] 写入失败 {exc}", flush=True)
                if ctl.client is not None and not ctl.client.is_connected:
                    await asyncio.sleep(0.5)
                    await ctl.connect()
                    print(f"  (已重连 {ctl.device.address})", flush=True)

        print("阶段1：首字节 0x00-0xFF")
        for p0 in range(0x100):
            await send(f"首{p0:02X}", [p0, 0, 0, 0, 0, 0, 0])

        print("\n阶段2：0x07 命令族子字节 0x00-0xFF（跳过已知）")
        for p1 in range(0x100):
            if p1 in (0x02, 0x03, 0x04, 0x05, 0xEA):
                continue
            await send(f"07-{p1:02X}", [0x07, p1, 0, 0, 0, 0, 0])

        print("\n阶段3：0x04 / 0x06 命令族子字节")
        for p0 in (0x04, 0x06):
            for p1 in range(0x100):
                await send(f"{p0:02X}-{p1:02X}", [p0, p1, 0, 0, 0, 0, 0])

        print("\n恢复默认状态：前灯开、亮度 80、色温 4500K")
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

        print(f"\n探测完成：通知 {len(notifications)} 条，导致断开的帧 {len(kills)} 个")
        for label, payload in kills:
            print(f"  断开帧 [{label}]: {hexs(bytes([0x7E, *payload, 0xEF]))}")


if __name__ == "__main__":
    asyncio.run(main())
