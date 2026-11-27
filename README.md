# 项目只暴露挂灯的蓝牙接口,抛砖引玉,有能力用ai改造成自己喜欢的东西也未尝不可

## THUNDEROBOT L2 屏幕挂灯 BLE 控制

雷神屏幕挂灯 L2 / THUNDEROBOT L2 的蓝牙控制封装。设备仅通过广播名称 `THUNDEROBOT L2` 探测，不依赖 MAC 地址（每台设备地址不同）。注意：挂灯与其他设备连接之后挂灯蓝牙暂时不可用。;依赖`THUNDEROBOT L2`设备名,如果有多个相同的挂灯需要注意一下

所有功能统一经 `L2Controller.dispatch(action, **params)` 下发，业务代码不直接访问 GATT。

## 文件结构

| 文件 | 用途 |
|---|---|
| `l2_core.py` | 统一封装：连接管理、命令注册表、唯一调度函数 |
| `l2_cli.py` | 命令行入口，全部中文/十进制参数 |
| `scan_l2.py` | 设备扫描与 GATT 枚举 |
| `probe/` | 18 个实验脚本，记录越界/绕路等探测过程 |

---

## 一、自己封装的函数（对外 API）

### 1.1 核心调度与生命周期 — `l2_core.py`

| 函数 | 签名 | 说明 |
|---|---|---|
| **`dispatch`** | `async (action: str, **params) -> list[bytes]` | **唯一调度出口**。所有功能（含未来新增）都必须经此下发 |
| `connect` | `async () -> Device` | 按广播名 `THUNDEROBOT L2` 探测并连接；可选订阅通知 |
| `disconnect` | `async () -> None` | 断开连接 |
| `scan` | `async (timeout: float = 8.0) -> list[Device]` | 扫描周边 BLE 设备 |
| `find` | `async (timeout: float = 8.0) -> Device` | 仅按广播名 `THUNDEROBOT L2` 精确匹配，不使用 MAC |
| `__aenter__` / `__aexit__` | 上下文管理 | 支持 `async with L2Controller() as ctl:` 自动连接/断开 |

### 1.2 功能薄封装（全部只做 `dispatch` 转发）

| 函数 | 签名 | 适用灯 | 说明 |
|---|---|---|---|
| `power` | `async (channel="front", on=True) -> bytes` | **前灯 + 后灯** | 开关；`channel` 选 `front`/`rear` |
| `brightness` | `async (channel="front", level=100) -> bytes` | **前灯 + 后灯** | 亮度；`channel` 选 `front`/`rear`，默认 `front` 即前灯 |
| `cct` | `async (kelvin=4500) -> bytes` | **仅前灯** | 标准色温 3000–6000K |
| `full_white` | `async () -> bytes` | **仅前灯** | 最亮白光（暖白+冷白两路全开） |
| `max_brightness` | `async () -> list[bytes]` | **仅前灯** | 最亮组合（前灯亮度100 + 两路全开） |
| `rgb` | `async (r=255, g=0, b=0, tag="solid") -> bytes` | **仅后灯** | 颜色；前灯不响应 RGB 帧 |
| `effect` | `async (mode="正向幻彩") -> bytes` | **仅后灯** | 47 种灯效 |
| `speed` | `async (level=50) -> bytes` | **仅后灯** | 灯效速度 |
| `query` | `async () -> bytes` | 通用 | 状态查询 |
| `clock` | `async (hour=None, minute=None, second=None) -> bytes` | 通用 | 设备对时 |
| `handshake` | `async () -> list[bytes]` | 通用 | 查询 + 对时两帧 |

### 1.3 模块级工具函数

| 函数 | 签名 | 说明 |
|---|---|---|
| `l2_call` | `async (action, **params) -> list[bytes]` | 一次性调用：按设备名连接 → dispatch → 断开 |
| `frame` | `(payload: Iterable[int]) -> bytes` | 把 7 字节 payload 封装成 `7E + payload + EF` |
| `hexs` | `(data: bytes) -> str` | 字节转 `XX XX ...` 十六进制字符串 |
| `clamp` | `(value, low, high) -> int` | 数值钳制 |
| `resolve_effect` | `(mode: str \| int) -> str` | 中文名/英文名/1–47 序号 → 内部键 |
| `register` | `(action: str) -> decorator` | 注册帧构造器到 `BUILDERS`，供 `dispatch` 调用 |

### 1.4 数据结构与常量

| 名称 | 说明 |
|---|---|
| `Device` | 设备信息：`address`、`name`、`display` 属性 |
| `BUILDERS` | 动作名 → 帧构造器注册表，共 12 个动作 |
| `CHANNEL_BYTE` | `{"rear": 0x01, "front": 0x05}` |
| `TAG_BYTE` | `{"solid": 0x10, "scroll": 0x20}` |
| `CCT_ANCHORS` | 色温锚点 `((3000,100),(4000,75),(4500,50),(5000,25),(6000,0))` |
| `EFFECTS` | 47 种灯效表：英文名 → `(MODE, 分组, 中文名)` |
| `FULL_WHITE_PAYLOAD` | 最亮白光固定 payload `[0x07,0x05,0x02,100,100,0x02,0x01]` |
| `HEAD` / `TAIL` | 帧头 `0x7E` / 帧尾 `0xEF` |
| `WRITE_GAP` | 写入间隔 55ms |
| `SERVICE_UUID` / `WRITE_UUID` / `NOTIFY_UUID` | GATT UUID |

---

## 二、统一帧表达框架

### 2.1 通用结构

所有 BLE 控制帧遵循同一结构：

```
7E  P0  P1  P2  P3  P4  P5  P6  EF
│   └──────── 7 字节 payload ────────┘
│                                    └─ 帧尾 0xEF
└─ 帧头 0x7E
```

写入特征 `0000FFF3-...`，`write-without-response`，帧间隔 55ms。

### 2.2 全部动作的帧表达（统一表）

| 动作 | P0 | P1 | P2 | P3 | P4 | P5 | P6 | 完整帧示例 |
|---|---|---|---|---|---|---|---|---|
| `power` | `07` | `04` | `XX` | `CH` | `YY` | `02` | `01` | `7E 07 04 FF 05 01 02 01 EF` |
| `brightness` | `04` | `01` | `LV` | `CH` | `FF` | `02` | `01` | `7E 04 01 64 05 FF 02 01 EF` |
| `cct` | `07` | `05` | `02` | `WW` | `CW` | `02` | `01` | `7E 07 05 02 32 32 02 01 EF` |
| `full_white` | `07` | `05` | `02` | `64` | `64` | `02` | `01` | `7E 07 05 02 64 64 02 01 EF` |
| `rgb` | `07` | `05` | `03` | `RR` | `GG` | `BB` | `TAG` | `7E 07 05 03 FF 00 00 10 EF` |
| `effect` | `07` | `03` | `MODE` | `06` | `FF` | `FF` | `00` | `7E 07 03 01 06 FF FF 00 EF` |
| `speed` | `07` | `02` | `SP` | `FF` | `FF` | `FF` | `00` | `7E 07 02 32 FF FF FF 00 EF` |
| `query` | `07` | `EA` | `02` | `01` | `FF` | `FF` | `00` | `7E 07 EA 02 01 FF FF 00 EF` |
| `clock` | `06` | `83` | `HH` | `MM` | `SS` | `06` | `00` | `7E 06 83 0A 1F 3C 06 00 EF` |
| `raw` | 任意 | 任意 | 任意 | 任意 | 任意 | 任意 | 任意 | 探测专用，自动加帧头帧尾 |

组合动作：

| 动作 | 由哪些帧组成 |
|---|---|
| `handshake` | `query` → `clock` |
| `max_brightness` | `brightness(前灯,100)` → `full_white` |

### 2.3 变量字段取值表

| 变量 | 出现位置 | 取值范围 |
|---|---|---|
| `CH` | `power` P3、`brightness` P3 | 前灯 `05`，后灯 `01`；`00` 为广播通道（同时控制前后灯，实测） |
| `XX` / `YY` | `power` P2 / P4 | 开：`FF` / `01`；关：`00` / `00` |
| `LV` | `brightness` P2 | 1–100 百分比 |
| `WW` / `CW` | `cct` P3 / P4 | 暖白/冷白份额，`WW+CW=100`；`full_white` 例外为 `64+64` |
| `RR` / `GG` / `BB` | `rgb` P3/P4/P5 | 各 0–255 |
| `TAG` | `rgb` P6 | 纯色 `10`，滚动 `20` |
| `MODE` | `effect` P2 | 0–255，47 种灯效见第五节 |
| `SP` | `speed` P2 | 1–100 百分比 |
| `HH` / `MM` / `SS` | `clock` P3/P4/P5 | 0–23 / 0–59 / 0–59 |

### 2.4 色温锚点表（`cct` 的 `WW`/`CW` 取值）

| 色温 | `WW` | `CW` | 帧 |
|---|---|---|---|
| 3000K | `64` | `00` | `7E 07 05 02 64 00 02 01 EF` |
| 4000K | `4B` | `19` | `7E 07 05 02 4B 19 02 01 EF` |
| 4500K | `32` | `32` | `7E 07 05 02 32 32 02 01 EF` |
| 5000K | `19` | `4B` | `7E 07 05 02 19 4B 02 01 EF` |
| 6000K | `00` | `64` | `7E 07 05 02 00 64 02 01 EF` |

中间色温按上表线性插值取整。

### 2.5 百分比编码规则（重要）

设备把百分比字节按**十进制两位数**解析，取后两位作为百分比，`00` 表示 100%：

```
100 → "00" → 100%     110 → "10" → 10%     200 → "00" → 100%
```

越界不会更亮，只会回绕成小数值（变暗）。因此封装函数对百分比参数严格校验 1–100，超出直接报错。

### 2.6 GATT 接口

| 服务 UUID | 特征 UUID | 属性 | 说明 |
|---|---|---|---|
| `00001800-...` | `00002A00-...` | read, notify | Device Name |
| `0000FFF0-...` | `0000FFF3-...` | read, **write-without-response** | 所有控制帧写入此处；读取值为固件串 `YG_P30_A28_V0031` |
| `0000FFF0-...` | `0000FFF4-...` | notify | 通知通道，探测中未见状态回包 |

---

## 三、快速开始

```bash
# 查看全部可用动作和灯效
.venv/bin/python.exe l2_cli.py list

# 最亮组合
.venv/bin/python.exe l2_cli.py max_brightness

# 前灯：开、亮度 80%、色温 4500K
.venv/bin/python.exe l2_cli.py power --channel 前灯 --state 开
.venv/bin/python.exe l2_cli.py brightness --channel 前灯 --level 80
.venv/bin/python.exe l2_cli.py cct --kelvin 4500

# 后灯：红色跑马、速度 50
.venv/bin/python.exe l2_cli.py effect --mode 红色跑马
.venv/bin/python.exe l2_cli.py speed --level 50

# 显示底层帧
.venv/bin/python.exe l2_cli.py --debug effect --mode 红色跑马
```

Python API：

```python
import asyncio
from l2_core import L2Controller

async def main():
    async with L2Controller() as ctl:
        await ctl.connect()
        await ctl.power(channel="前灯", on=True)
        await ctl.brightness(channel="前灯", level=80)
        await ctl.cct(kelvin=4500)
        await ctl.effect("红色跑马")
        await ctl.speed(50)

asyncio.run(main())
```

## 四、接口参数说明

各动作的帧表达见第二节统一表，这里只列参数与行为。

### 4.1 `power` — 前灯/后灯电源

同一个接口通过 `channel` 区分两路，默认 `front`。

| 参数 | 取值 |
|---|---|
| `channel` | `front`/`前灯` → 前灯；`rear`/`后灯` → 后灯 |
| `on` | `True` 开、`False` 关 |

```bash
l2_cli.py power --channel 前灯 --state 开
l2_cli.py power --channel 后灯 --state 关
```

### 4.2 `brightness` — 前灯/后灯亮度

同一个接口通过 `channel` 区分两路：传 `front` 调前灯，传 `rear` 调后灯；默认 `front`。

| 参数 | 取值 |
|---|---|
| `channel` | `front`/`前灯` → 前灯；`rear`/`后灯` → 后灯 |
| `level` | 1–100（百分比，越界报错） |

```bash
l2_cli.py brightness --channel 前灯 --level 80
l2_cli.py brightness --channel 后灯 --level 60
```

### 4.3 `cct` — 标准色温

| 参数 | 取值 |
|---|---|
| `kelvin` | 3000–6000K，超出自动钳制 |

`WW+CW=100` 的标准双色调和，锚点见 2.4 节。

### 4.4 `full_white` — 最亮白光

无参数。官方4500K默认是`WW=50, CW=50`,这个flag把WW和CW都拉到`WW=100, CW=100`,不知道开发者咋想的,为什么会把冷灯和暖灯只调到50。两路比例 1:1 所以仍是中间色温，但都满功率，比 4500K 标准帧亮一倍。

### 4.5 `max_brightness` — 最亮组合

无参数。依次发前灯亮度 100% + 两路全开。

### 4.6 `rgb` — 后灯颜色

| 参数 | 取值 |
|---|---|
| `r`, `g`, `b` | 各 0–255 |
| `tag` | `solid`/`纯色` → `10`；`scroll`/`滚动` → `20` |

`solid` 整条涂色；`scroll` 把颜色推入灯带，配合音乐律动。

### 4.7 `effect` — 后灯灯效

| 参数 | 取值 |
|---|---|
| `mode` | 中文名、英文名或 1–47 序号，三种写法等价 |

47 种灯效见第五节。

### 4.8 `speed` — 后灯灯效速度

| 参数 | 取值 |
|---|---|
| `level` | 1–100（百分比），仅灯效模式下生效 |

### 4.9 `query` / `clock` / `handshake` — 握手

- `query`：状态查询，握手首帧
- `clock`：设备对时，省略参数取本机当前时间
- `handshake`：依次发 `query` + `clock`

### 4.10 `raw` — 原始帧（仅探测用）

| 参数 | 取值 |
|---|---|
| `payload` | 任意 7 字节列表，自动封装帧头帧尾 |

正式功能不应使用此接口。

---

## 五、前灯调节的全部内容

前灯是 108 颗冷暖双色 LED，只有白光，不支持 RGB。

| 功能 | 接口 | 范围/说明 |
|---|---|---|
| 电源开关 | `power(channel="前灯")` | 开/关 |
| 亮度 | `brightness(channel="前灯", level=...)` | 1–100% |
| 标准色温 | `cct(kelvin=...)` | 3000–6000K，双色调和，`WW+CW=100` |
| 最亮白光 | `full_white()` | 两路各 100%，非标准色温 |
| 一键最亮 | `max_brightness()` | 亮度 100% + 两路全开 |

前灯：
- 不接受 RGB 帧（实测不响应）
- 没有灯效、速度、音乐律动
- 亮度/色温字节越界只会回绕变暗

## 六、后灯调节的全部内容

后灯是 34 颗 RGB 灯珠。

| 功能 | 接口 | 范围/说明 |
|---|---|---|
| 电源开关 | `power(channel="后灯")` | 开/关 |
| 亮度 | `brightness(channel="后灯", level=...)` | 1–100% |
| 固定颜色 | `rgb(tag="纯色")` | R/G/B 各 0–255 |
| 颜色推进 | `rgb(tag="滚动")` | 配合音乐律动 |
| 灯效 | `effect(mode=...)` | 47 种，见下表 |
| 速度 | `speed(level=...)` | 1–100%，仅灯效模式下生效 |

## 七、后灯全部 47 种灯效

`--mode` 可写中文名、英文名或序号。帧中 `MODE` 字段取值见下表。

| 序号 | 分组 | 中文名 | 英文名 | MODE |
|---:|---|---|---|---|
| 1 | 幻彩 | 自动循环 | `AutoLoop` | `0x00` |
| 2 | 幻彩 | 正向幻彩 | `RainbowFwd` | `0x01` |
| 3 | 幻彩 | 反向幻彩 | `RainbowRev` | `0x02` |
| 4 | 幻彩 | 七彩能量 | `RainbowEnergy` | `0xD4` |
| 5 | 跳变 | 七彩跳变 | `RainbowJump` | `0xC1` |
| 6 | 跳变 | 红绿蓝跳变 | `RgbJump` | `0xC2` |
| 7 | 跳变 | 黄青紫跳变 | `YcmJump` | `0xC3` |
| 8 | 跳变 | 七彩频闪 | `RainbowStrobe` | `0xC4` |
| 9 | 跳变 | 红绿蓝频闪 | `RgbStrobe` | `0xC5` |
| 10 | 跳变 | 黄青紫频闪 | `YcmStrobe` | `0xC6` |
| 11 | 跳变 | 七色渐变 | `SevenFade` | `0xC7` |
| 12 | 跳变 | 红黄交替渐变 | `RedYellowFade` | `0xC8` |
| 13 | 跳变 | 红紫交替渐变 | `RedPurpleFade` | `0xC9` |
| 14 | 跳变 | 绿青交替渐变 | `GreenCyanFade` | `0xCA` |
| 15 | 跳变 | 绿黄交替渐变 | `GreenYellowFade` | `0xCB` |
| 16 | 跳变 | 蓝紫交替渐变 | `BluePurpleFade` | `0xCC` |
| 17 | 跑马 | 红色跑马 | `RedHorse` | `0xCD` |
| 18 | 跑马 | 绿色跑马 | `GreenHorse` | `0xCE` |
| 19 | 跑马 | 蓝色跑马 | `BlueHorse` | `0xCF` |
| 20 | 跑马 | 黄色跑马 | `YellowHorse` | `0xD0` |
| 21 | 跑马 | 青色跑马 | `CyanHorse` | `0xD1` |
| 22 | 跑马 | 紫色跑马 | `PurpleHorse` | `0xD2` |
| 23 | 跑马 | 白色跑马 | `WhiteHorse` | `0xD3` |
| 24 | 追光 | 正向七彩追光 | `RainbowFollowFwd` | `0x4D` |
| 25 | 追光 | 反向七彩追光 | `RainbowFollowRev` | `0x4E` |
| 26 | 追光 | 正向红绿蓝追光 | `RgbFollowFwd` | `0x4F` |
| 27 | 追光 | 反向红绿蓝追光 | `RgbFollowRev` | `0x50` |
| 28 | 追光 | 正向黄青紫追光 | `YcmFollowFwd` | `0x51` |
| 29 | 追光 | 反向黄青紫追光 | `YcmFollowRev` | `0x52` |
| 30 | 飘动 | 正向七彩飘动 | `RainbowDriftFwd` | `0x53` |
| 31 | 飘动 | 反向七彩飘动 | `RainbowDriftRev` | `0x54` |
| 32 | 飘动 | 正向红绿蓝飘动 | `RgbDriftFwd` | `0x55` |
| 33 | 飘动 | 反向红绿蓝飘动 | `RgbDriftRev` | `0x56` |
| 34 | 飘动 | 正向黄青紫飘动 | `YcmDriftFwd` | `0x57` |
| 35 | 飘动 | 反向黄青紫飘动 | `YcmDriftRev` | `0x58` |
| 36 | 刷色 | 正向七彩刷色 | `RainbowBrushFwd` | `0xB5` |
| 37 | 刷色 | 反向七彩刷色 | `RainbowBrushRev` | `0xB6` |
| 38 | 刷色 | 正向红绿蓝刷色 | `RgbBrushFwd` | `0xB7` |
| 39 | 刷色 | 反向红绿蓝刷色 | `RgbBrushRev` | `0xB8` |
| 40 | 刷色 | 正向黄青紫刷色 | `YcmBrushFwd` | `0xB9` |
| 41 | 刷色 | 反向黄青紫刷色 | `YcmBrushRev` | `0xBA` |
| 42 | 刷色 | 七彩刷色闭幕 | `RainbowBrushClose` | `0xBB` |
| 43 | 刷色 | 七彩刷色拉幕 | `RainbowBrushOpen` | `0xBC` |
| 44 | 刷色 | 红绿蓝刷色闭幕 | `RgbBrushClose` | `0xBD` |
| 45 | 刷色 | 红绿蓝刷色拉幕 | `RgbBrushOpen` | `0xBE` |
| 46 | 刷色 | 黄青紫刷色闭幕 | `YcmBrushClose` | `0xBF` |
| 47 | 刷色 | 黄青紫刷色拉幕 | `YcmBrushOpen` | `0xC0` |

```bash
l2_cli.py effect --mode 红色跑马
l2_cli.py effect --mode 17
l2_cli.py effect --mode RedHorse
```

三种写法等价。

---

## 八、实验结论（已排除的路径）

真机探测记录在 `probe/`，以下路径全部验证无效，勿重复尝试：

| 尝试 | 结果 |
|---|---|
| 亮度/色温字节越界（110、120、128、200、255） | 回绕成小数值，变暗 |
| 前灯发 RGB 帧 | 不响应 |
| 固件刷写 | 没找到入口,可能就是设计死的吧? |
| 隐藏命令 | 全码扫描无响应 |

**亮度上限**：`full_white` + 前灯亮度 100% 是协议能表达的硬件上限。再亮需改硬件（驱动电流/灯珠）。

**未实现但官方声称的功能**：
- 音乐律动/MIC 拾音：设备端只认 `rgb(tag="滚动")` 帧，音频分析需在主机侧完成
- 环境光自动补光：设备端有光感，但协议未暴露控制接口
- 定时关闭：蓝牙开放的功能没发现有定时器(可能没找到?),只能由一个外部设备去控制灯定时开关

## 九、扩展方式

新增功能只需注册帧构造器，再经 `dispatch()` 调度：

```python
@register("new_action")
def _new_action(x: int) -> bytes:
    return frame([...])

await ctl.dispatch("new_action", x=1)
```

`l2_cli.py` 的 `list` 子命令会自动列出所有已注册动作。
