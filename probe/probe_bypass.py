#!/usr/bin/env python3
"""实验性绕路：假设两位数判断可被绕过，测试三条可能路径。

路径1：LV 全值扫描 —— 若固件内部是查表而非取模，某些字节可能映射到 >100% PWM
路径2：power 帧 XX 字节 —— 源码只用于开关，但可能藏有增益/强度含义
路径3：未文档化通道 —— CH=05(前)/01(后)，其他值可能触发组合/增益通道
路径4：帧长度变异 —— 多塞一字节，看设备是否按不同偏移解析

每组先发 6000K 锁基线，每步按 Enter 观察，q 结束。
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
        print("前置：前灯开、6000K 冷白单路\n")

        async def reconnect() -> None:
            await asyncio.sleep(0.6)
            await ctl.connect()
            await ctl.dispatch("power", channel="front", on=True)
            await asyncio.sleep(0.1)
            print("  (已重连并重新开灯)")

        async def send_with_retry(payload: list[int]) -> list[bytes]:
            for attempt in range(2):
                try:
                    if not ctl.client.is_connected:
                        await reconnect()
                    return await ctl.dispatch("raw", payload=payload)
                except Exception as exc:
                    print(f"  写入异常（第 {attempt + 1} 次）: {exc}")
                    if attempt == 0:
                        await reconnect()
            raise RuntimeError("写入失败且重连后仍失败")

        async def step(label: str, payload: list[int], note: str) -> bool:
            try:
                await send_with_retry(CCT_6000K)
                await asyncio.sleep(0.08)
                frames = await send_with_retry(payload)
            except Exception as exc:
                print(f"[{label}] 发送失败: {exc}")
                return True
            print(f"[{label}] {hexs(frames[0])}")
            print(f"  {note}")
            try:
                answer = input("  观察完按 Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                return False
            return answer != "q"

        print("=== 路径1：LV 查表魔法值（找比 100 更亮的值）===")
        for label, lv, note in [
            ("基准 LV=100", 100, "记住这个亮度"),
            ("LV=0", 0, "若也是100%，证明00→100%是取模；若更亮就是魔法值"),
            ("LV=99", 99, "对比"),
            ("LV=128", 128, "对比"),
            ("LV=200", 200, "对比"),
            ("LV=255", 255, "对比"),
        ]:
            if not await step(f"LV={lv}", [0x04, 0x01, lv, 0x05, 0xFF, 0x02, 0x01], note):
                break

        print("\n=== 路径2：power 帧 XX 字节（源码只当开关）===")
        for xx in (0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF):
            note = "标准开" if xx == 0xFF else "更亮？更暗？无效？"
            if not await step(f"XX={xx:02X}", [0x07, 0x04, xx, 0x05, 0x01, 0x02, 0x01], note):
                break

        print("\n=== 路径3：未文档化通道 CH ===")
        for ch in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
            note = "标准前灯" if ch == 0x05 else ("标准后灯" if ch == 0x01 else "有反应吗？")
            if not await step(f"CH={ch:02X}", [0x04, 0x01, 100, ch, 0xFF, 0x02, 0x01], note):
                break

        print("\n=== 路径4：帧长度变异（payload 8 字节）===")
        for extra in (0x00, 0x01, 0x64, 0xFF):
            payload = [0x04, 0x01, 100, 0x05, 0xFF, 0x02, 0x01, extra]
            try:
                await send_with_retry(CCT_6000K)
                await asyncio.sleep(0.08)
                frames = await ctl.dispatch("raw", payload=payload + [extra])
            except Exception as exc:
                print(f"  额外字节 {extra:02X} 发送失败: {exc}")
                continue
            data = frames[0]
            print(f"[额外字节 {extra:02X}] {hexs(data)}")
            try:
                answer = input("  有变化、闪烁、断开？Enter 继续（q 结束）: ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break

        print("\n恢复默认")
        if not ctl.client.is_connected:
            await ctl.connect()
        for action, params in [
            ("power", {"channel": "front", "on": True}),
            ("brightness", {"channel": "front", "level": 100}),
            ("cct", {"kelvin": 4500}),
        ]:
            await ctl.dispatch(action, **params)
            await asyncio.sleep(0.06)


if __name__ == "__main__":
    asyncio.run(main())
