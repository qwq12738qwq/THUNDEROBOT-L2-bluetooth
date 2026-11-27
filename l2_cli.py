#!/usr/bin/env python3
"""THUNDEROBOT L2 命令行：全部用中文/十进制参数，十六进制只在内部使用。"""
from __future__ import annotations

import argparse
import asyncio

from l2_core import (
    BUILDERS, CHANNEL_BYTE, EFFECTS, EFFECT_NAMES, TAG_BYTE,
    L2Controller, hexs, resolve_effect,
)

CHANNEL_CN = {"前灯": "front", "后灯": "rear"}
CHANNEL_DISPLAY = {"front": "前灯", "rear": "后灯"}
STATE_CN = {"开": "on", "关": "off"}
TAG_CN = {"纯色": "solid", "滚动": "scroll"}


def notify(sender, data: bytes) -> None:
    print(f"  <<< 收到状态通知 {hexs(data)}", flush=True)


def describe(action: str, p: dict) -> str:
    if action == "power":
        return f"{CHANNEL_DISPLAY.get(p['channel'], p['channel'])} → {'打开' if p['on'] else '关闭'}"
    if action == "brightness":
        return f"{CHANNEL_DISPLAY.get(p['channel'], p['channel'])}亮度 → {p['level']}%"
    if action == "cct":
        return f"色温 → {p['kelvin']}K"
    if action == "full_white":
        return "最亮白光 → 暖白100 + 冷白100（两路全开）"
    if action == "max_brightness":
        return "最亮组合 → 前灯亮度100% + 两路全开"
    if action == "rgb":
        tag = "纯色" if p["tag"] == "solid" else "滚动"
        return f"颜色 → 红{p['r']} 绿{p['g']} 蓝{p['b']}（{tag}）"
    if action == "effect":
        name = resolve_effect(p["mode"])
        code, group, cn = EFFECTS[name]
        return f"灯效 → {cn}（{group}，第 {EFFECT_NAMES.index(name) + 1} 种）"
    if action == "speed":
        return f"灯效速度 → {p['level']}"
    return f"{action} 已发送"


async def run(args: argparse.Namespace) -> None:
    async with L2Controller(notify_callback=notify if args.notify else None) as ctl:
        dev = await ctl.connect()
        print(f"已连接 {dev.display} ({dev.address})")

        if args.action == "list":
            print("\n可用动作（括号内为常用参数）：")
            print("  power(前/后灯, 开/关)  brightness(前/后灯, 1-100)")
            print("  cct(3000-6000K)  rgb(红绿蓝 0-255, 纯色/滚动)")
            print("  effect(中文名/序号)  speed(1-100)  query  clock  handshake")
            print("\n通道：front=前灯   rear=后灯")
            print("颜色模式：solid=纯色   scroll=滚动")
            print("\n灯效列表（--mode 后可写中文名、英文名或序号）：")
            for i, name in enumerate(EFFECT_NAMES, 1):
                _, group, cn = EFFECTS[name]
                print(f"  {i:2d}. [{group}] {cn}")
            return

        params = vars(args).copy()
        for key in ("action", "notify", "wait", "func", "debug"):
            params.pop(key, None)
        if "channel" in params:
            params["channel"] = CHANNEL_CN.get(params["channel"], params["channel"])
        if args.action == "power":
            state = params.pop("state")
            params["on"] = STATE_CN.get(state, state) == "on"
        if args.action == "rgb" and "tag" in params:
            params["tag"] = TAG_CN.get(params["tag"], params["tag"])
        if args.action == "effect":
            mode = params.get("mode")
            if isinstance(mode, str) and mode.isdigit():
                params["mode"] = int(mode)

        frames = await ctl.dispatch(args.action, **params)
        print(f"完成：{describe(args.action, params)}")
        if args.debug:
            for data in frames:
                print(f"  [调试帧] {hexs(data)}")

        wait = getattr(args, "wait", 0)
        if wait:
            print(f"等待 {wait} 秒接收通知...")
            await asyncio.sleep(wait)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="THUNDEROBOT L2 统一调度命令行（无需写十六进制）")
    p.add_argument("--notify", action="store_true", help="订阅状态通知")
    p.add_argument("--debug", action="store_true", help="显示底层帧（仅调试用）")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("list", help="列出支持的动作、通道和全部中文灯效")
    sub.add_parser("query", help="查询设备状态")
    sub.add_parser("clock", help="同步本地时间")

    hp = sub.add_parser("handshake", help="连接后握手（查询 + 对时）")
    hp.add_argument("--wait", type=float, default=0)

    pp = sub.add_parser("power", help="开关灯")
    pp.add_argument("--channel", default="front", choices=list(CHANNEL_BYTE) + list(CHANNEL_CN))
    pp.add_argument("--state", default="on", choices=["on", "off", "开", "关"])

    bp = sub.add_parser("brightness", help="设置亮度，1 到 100")
    bp.add_argument("--channel", default="front", choices=list(CHANNEL_BYTE) + list(CHANNEL_CN))
    bp.add_argument("--level", type=int, default=100)

    cp = sub.add_parser("cct", help="设置色温，3000 到 6000")
    cp.add_argument("--kelvin", type=int, default=4500)

    sub.add_parser("full_white", help="最亮白光：暖白100 + 冷白100（两路全开）")
    sub.add_parser("max_brightness", help="最亮组合：亮度100% + 两路全开")

    rp = sub.add_parser("rgb", help="设置颜色，每个通道 0 到 255")
    rp.add_argument("--r", type=int, default=255)
    rp.add_argument("--g", type=int, default=0)
    rp.add_argument("--b", type=int, default=0)
    rp.add_argument("--tag", default="solid", choices=list(TAG_BYTE) + list(TAG_CN))

    ep = sub.add_parser("effect", help="设置灯效，写中文名或序号")
    ep.add_argument("--mode", default="正向幻彩")

    sp = sub.add_parser("speed", help="设置灯效速度，1 到 100")
    sp.add_argument("--level", type=int, default=50)

    for parser in (hp, pp, bp, cp, rp, ep, sp):
        parser.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                            help="显示底层帧（仅调试用）")
    return p


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
