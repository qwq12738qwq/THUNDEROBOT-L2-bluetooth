#!/usr/bin/env python3
"""THUNDEROBOT L2 统一封装：所有功能必须经 L2Controller.dispatch() 调度。

协议帧格式（抓包逆向）：7E + 7 字节 payload + EF，写入 FFF3 特征。

百分比参数编码规则（真机验证）：设备把亮度/色温字节当作十进制两位数解析，
取后两位作为百分比，"00" 表示 100%。因此：
    100 -> "00" -> 100%   110 -> "10" -> 10%   200 -> "00" -> 100%
即 1 字节只能表达 1-100，越界会回绕成小数值（变暗），不是更大亮度。
所以 percentage 必须先钳制到 1-100 再编码，不能靠传大数值"超频"。

真机实验已排除的软件提速路径（全部无效，勿重复尝试）：
- 亮度帧保留字节 FF/02/01 改成任意值：无变化
- 连发亮度帧 5/20/100 次：覆盖式，不累加
- 前灯发 RGB 帧：不响应
- 固件不可刷写（无 OTA/DFU 特征），无隐藏命令（全码扫描无响应）
亮度 100 + CCT 双路 100 已是协议能表达的硬件上限，再亮只能改硬件。

新增功能只需用 @register("动作名") 注册帧构造器，再通过 dispatch 调用。
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"
DEVICE_NAME = "THUNDEROBOT L2"

HEAD = 0x7E
TAIL = 0xEF
WRITE_GAP = 0.055


def frame(payload: Iterable[int]) -> bytes:
    body = list(payload)
    if len(body) != 7:
        raise ValueError(f"payload 必须为 7 字节，实际 {len(body)}")
    return bytes([HEAD, *body, TAIL])


def hexs(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


CHANNEL_BYTE = {"rear": 0x01, "front": 0x05}
TAG_BYTE = {"solid": 0x10, "scroll": 0x20}
CCT_ANCHORS = ((3000, 100), (4000, 75), (4500, 50), (5000, 25), (6000, 0))
EFFECTS: dict[str, tuple[int, str, str]] = {
    "AutoLoop": (0x00, "幻彩", "自动循环"),
    "RainbowFwd": (0x01, "幻彩", "正向幻彩"),
    "RainbowRev": (0x02, "幻彩", "反向幻彩"),
    "RainbowEnergy": (0xD4, "幻彩", "七彩能量"),
    "RainbowJump": (0xC1, "跳变", "七彩跳变"),
    "RgbJump": (0xC2, "跳变", "红绿蓝跳变"),
    "YcmJump": (0xC3, "跳变", "黄青紫跳变"),
    "RainbowStrobe": (0xC4, "跳变", "七彩频闪"),
    "RgbStrobe": (0xC5, "跳变", "红绿蓝频闪"),
    "YcmStrobe": (0xC6, "跳变", "黄青紫频闪"),
    "SevenFade": (0xC7, "跳变", "七色渐变"),
    "RedYellowFade": (0xC8, "跳变", "红黄交替渐变"),
    "RedPurpleFade": (0xC9, "跳变", "红紫交替渐变"),
    "GreenCyanFade": (0xCA, "跳变", "绿青交替渐变"),
    "GreenYellowFade": (0xCB, "跳变", "绿黄交替渐变"),
    "BluePurpleFade": (0xCC, "跳变", "蓝紫交替渐变"),
    "RedHorse": (0xCD, "跑马", "红色跑马"),
    "GreenHorse": (0xCE, "跑马", "绿色跑马"),
    "BlueHorse": (0xCF, "跑马", "蓝色跑马"),
    "YellowHorse": (0xD0, "跑马", "黄色跑马"),
    "CyanHorse": (0xD1, "跑马", "青色跑马"),
    "PurpleHorse": (0xD2, "跑马", "紫色跑马"),
    "WhiteHorse": (0xD3, "跑马", "白色跑马"),
    "RainbowFollowFwd": (0x4D, "追光", "正向七彩追光"),
    "RainbowFollowRev": (0x4E, "追光", "反向七彩追光"),
    "RgbFollowFwd": (0x4F, "追光", "正向红绿蓝追光"),
    "RgbFollowRev": (0x50, "追光", "反向红绿蓝追光"),
    "YcmFollowFwd": (0x51, "追光", "正向黄青紫追光"),
    "YcmFollowRev": (0x52, "追光", "反向黄青紫追光"),
    "RainbowDriftFwd": (0x53, "飘动", "正向七彩飘动"),
    "RainbowDriftRev": (0x54, "飘动", "反向七彩飘动"),
    "RgbDriftFwd": (0x55, "飘动", "正向红绿蓝飘动"),
    "RgbDriftRev": (0x56, "飘动", "反向红绿蓝飘动"),
    "YcmDriftFwd": (0x57, "飘动", "正向黄青紫飘动"),
    "YcmDriftRev": (0x58, "飘动", "反向黄青紫飘动"),
    "RainbowBrushFwd": (0xB5, "刷色", "正向七彩刷色"),
    "RainbowBrushRev": (0xB6, "刷色", "反向七彩刷色"),
    "RgbBrushFwd": (0xB7, "刷色", "正向红绿蓝刷色"),
    "RgbBrushRev": (0xB8, "刷色", "反向红绿蓝刷色"),
    "YcmBrushFwd": (0xB9, "刷色", "正向黄青紫刷色"),
    "YcmBrushRev": (0xBA, "刷色", "反向黄青紫刷色"),
    "RainbowBrushClose": (0xBB, "刷色", "七彩刷色闭幕"),
    "RainbowBrushOpen": (0xBC, "刷色", "七彩刷色拉幕"),
    "RgbBrushClose": (0xBD, "刷色", "红绿蓝刷色闭幕"),
    "RgbBrushOpen": (0xBE, "刷色", "红绿蓝刷色拉幕"),
    "YcmBrushClose": (0xBF, "刷色", "黄青紫刷色闭幕"),
    "YcmBrushOpen": (0xC0, "刷色", "黄青紫刷色拉幕"),
}

EFFECT_NAMES = list(EFFECTS)
EFFECT_CN_TO_KEY = {cn: key for key, (_, _, cn) in EFFECTS.items()}


def resolve_effect(mode: str | int) -> str:
    """把中文名、英文名或 1-47 序号转成内部键；调用方无需写十六进制。"""
    if isinstance(mode, int):
        if 1 <= mode <= len(EFFECT_NAMES):
            return EFFECT_NAMES[mode - 1]
        raise ValueError(f"灯效序号需在 1-{len(EFFECT_NAMES)} 之间")
    key = str(mode).strip()
    if key in EFFECTS:
        return key
    if key in EFFECT_CN_TO_KEY:
        return EFFECT_CN_TO_KEY[key]
    raise ValueError(f"未知灯效 {mode!r}，请用 list 子命令查看中文名称")


@dataclass(frozen=True)
class Device:
    address: str
    name: str | None

    @property
    def display(self) -> str:
        return self.name or self.address


# ---------------------------------------------------------------------------
# 命令注册表：所有功能帧构造器都注册到这里，dispatch 是唯一调度出口
# ---------------------------------------------------------------------------
BUILDERS: dict[str, Callable[..., bytes | list[bytes]]] = {}


def register(action: str):
    def deco(fn):
        BUILDERS[action] = fn
        return fn
    return deco


CHANNEL_ALIASES = {"前灯": "front", "后灯": "rear"}
TAG_ALIASES = {"纯色": "solid", "滚动": "scroll"}


def _channel(value: str) -> int:
    key = str(value).lower()
    key = CHANNEL_ALIASES.get(key, key)
    if key not in CHANNEL_BYTE:
        raise ValueError(f"未知通道 {value!r}，可用: 前灯/后灯")
    return CHANNEL_BYTE[key]


def _level(value: int) -> int:
    """百分比编码：只接受 1-100。越界会回绕成小数（110 -> 10%），必须拒绝。"""
    if not 1 <= int(value) <= 100:
        raise ValueError(f"百分比必须在 1-100 之间，收到 {value}；越界会回绕变暗")
    return int(value)


@register("raw")
def _raw(payload: list[int] | bytes) -> bytes:
    """协议探测用：直接封装任意 7 字节 payload。"""
    return frame(list(payload))


@register("power")
def _power(channel: str = "front", on: bool = True) -> bytes:
    xx, yy = (0xFF, 0x01) if on else (0x00, 0x00)
    return frame([0x07, 0x04, xx, _channel(channel), yy, 0x02, 0x01])


@register("brightness")
def _brightness(channel: str = "front", level: int = 100) -> bytes:
    return frame([0x04, 0x01, _level(level), _channel(channel), 0xFF, 0x02, 0x01])


def _warm_from_kelvin(kelvin: int) -> int:
    k = clamp(kelvin, 3000, 6000)
    for (k1, w1), (k2, w2) in zip(CCT_ANCHORS, CCT_ANCHORS[1:]):
        if k <= k2:
            return round(w1 + (w2 - w1) * (k - k1) / (k2 - k1))
    return 0


@register("cct")
def _cct(kelvin: int = 4500) -> bytes:
    warm = clamp(_warm_from_kelvin(kelvin), 0, 100)
    return frame([0x07, 0x05, 0x02, warm, 100 - warm, 0x02, 0x01])


# 真机实测最亮的白光组合：两路各自拉满，总和 200（非标准 CCT）。
# 标准色温受 WW+CW=100 约束；此帧绕过该约束，是灯体能达到的最大白光输出。
FULL_WHITE_PAYLOAD = [0x07, 0x05, 0x02, 100, 100, 0x02, 0x01]


@register("full_white")
def _full_white() -> bytes:
    """两路全开（WW=100, CW=100），真机实测的最亮白光固定参数。"""
    return frame(FULL_WHITE_PAYLOAD)


@register("max_brightness")
def _max_brightness() -> list[bytes]:
    """最亮组合：前灯亮度 100% + 两路全开，注册以便 CLI 经 dispatch 调度。"""
    return [_brightness(channel="front", level=100), _full_white()]


@register("rgb")
def _rgb(r: int = 255, g: int = 0, b: int = 0, tag: str = "solid") -> bytes:
    key = str(tag).lower()
    key = TAG_ALIASES.get(key, key)
    if key not in TAG_BYTE:
        raise ValueError(f"未知颜色模式 {tag!r}，可用: 纯色/滚动")
    return frame([0x07, 0x05, 0x03, clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255), TAG_BYTE[key]])


@register("effect")
def _effect(mode: str | int = "正向幻彩") -> bytes:
    name = resolve_effect(mode)
    code = EFFECTS[name][0]
    return frame([0x07, 0x03, code, 0x06, 0xFF, 0xFF, 0x00])


@register("speed")
def _speed(level: int = 50) -> bytes:
    return frame([0x07, 0x02, _level(level), 0xFF, 0xFF, 0xFF, 0x00])


@register("query")
def _query() -> bytes:
    return frame([0x07, 0xEA, 0x02, 0x01, 0xFF, 0xFF, 0x00])


@register("clock")
def _clock(hour: int | None = None, minute: int | None = None, second: int | None = None) -> bytes:
    now = time.localtime()
    h = clamp(now.tm_hour if hour is None else hour, 0, 23)
    m = clamp(now.tm_min if minute is None else minute, 0, 59)
    s = clamp(now.tm_sec if second is None else second, 0, 59)
    return frame([0x06, 0x83, h, m, s, 0x06, 0x00])


@register("handshake")
def _handshake() -> list[bytes]:
    return [_query(), _clock()]


# ---------------------------------------------------------------------------
# 统一封装：连接管理 + 唯一调度函数
# ---------------------------------------------------------------------------
class L2Controller:
    """所有灯控功能的唯一入口；业务代码只调用 dispatch，不直接写 GATT。"""

    def __init__(self, timeout: float = 15.0, notify_callback=None):
        self.timeout = timeout
        self.notify_callback = notify_callback
        self.client: BleakClient | None = None
        self.device: Device | None = None
        self._last_write = 0.0

    async def scan(self, timeout: float = 8.0) -> list[Device]:
        found = await BleakScanner.discover(timeout=timeout)
        return [Device(d.address, d.name) for d in found]

    async def find(self, timeout: float = 8.0) -> Device:
        """仅按广播名称 THUNDEROBOT L2 探测，不使用 MAC 地址。"""
        devices = await self.scan(timeout)
        hit = next(
            (d for d in devices if d.name and d.name.strip().upper() == DEVICE_NAME),
            None,
        )
        if hit is None:
            raise RuntimeError(f"未发现设备 {DEVICE_NAME}，请确认设备已开机并可发现")
        return hit

    async def connect(self) -> Device:
        self.device = await self.find()
        self.client = BleakClient(self.device.address, timeout=self.timeout)
        await self.client.connect()
        if self.notify_callback:
            await self.client.start_notify(NOTIFY_UUID, self.notify_callback)
        return self.device

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            if self.notify_callback:
                await self.client.stop_notify(NOTIFY_UUID)
            await self.client.disconnect()
        self.client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def _write(self, data: bytes) -> None:
        if self.client is None or not self.client.is_connected:
            raise RuntimeError("设备未连接，请先调用 connect()")
        gap = WRITE_GAP - (time.monotonic() - self._last_write)
        if gap > 0:
            await asyncio.sleep(gap)
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)
        self._last_write = time.monotonic()

    async def dispatch(self, action: str, **params) -> list[bytes]:
        """唯一调度函数：所有功能（含未来新增）都必须经此下发。"""
        builder = BUILDERS.get(action)
        if builder is None:
            raise ValueError(f"未知 action {action!r}，可用: {', '.join(BUILDERS)}")
        result = builder(**params)
        frames = [result] if isinstance(result, bytes) else list(result)
        for data in frames:
            await self._write(data)
        return frames

    # ---- 以下方法均为 dispatch 的薄封装，不直接访问 GATT ----
    async def power(self, channel: str = "front", on: bool = True) -> bytes:
        return (await self.dispatch("power", channel=channel, on=on))[0]

    async def brightness(self, channel: str = "front", level: int = 100) -> bytes:
        return (await self.dispatch("brightness", channel=channel, level=level))[0]

    async def cct(self, kelvin: int = 4500) -> bytes:
        return (await self.dispatch("cct", kelvin=kelvin))[0]

    async def full_white(self) -> bytes:
        return (await self.dispatch("full_white"))[0]

    async def max_brightness(self) -> list[bytes]:
        """最亮组合：前灯亮度拉满 + 两路色温全开。"""
        return [
            await self.brightness(channel="front", level=100),
            await self.full_white(),
        ]

    async def rgb(self, r: int = 255, g: int = 0, b: int = 0, tag: str = "solid") -> bytes:
        return (await self.dispatch("rgb", r=r, g=g, b=b, tag=tag))[0]

    async def effect(self, mode: str | int = "RainbowFwd") -> bytes:
        return (await self.dispatch("effect", mode=mode))[0]

    async def speed(self, level: int = 50) -> bytes:
        return (await self.dispatch("speed", level=level))[0]

    async def query(self) -> bytes:
        return (await self.dispatch("query"))[0]

    async def clock(self, **params) -> bytes:
        return (await self.dispatch("clock", **params))[0]

    async def handshake(self) -> list[bytes]:
        return await self.dispatch("handshake")


async def l2_call(action: str, **params) -> list[bytes]:
    """一次性调用：按设备名连接 → dispatch → 断开。"""
    async with L2Controller() as ctl:
        await ctl.connect()
        return await ctl.dispatch(action, **params)
