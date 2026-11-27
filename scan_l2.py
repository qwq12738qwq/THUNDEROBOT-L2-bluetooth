#!/usr/bin/env python3
"""扫描并枚举 THUNDEROBOT L2 的 BLE 服务与特征值（仅终端输出）。"""
import asyncio

from bleak import BleakClient, BleakScanner


def fmt_value(data: bytes) -> str:
    hex_str = data.hex(" ")
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{hex_str}  |  {text}"


async def scan(timeout: float = 10.0):
    print(f"扫描 BLE 设备（{timeout} 秒）...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        print(f"  [{d.address}] {d.name!r}  rssi={getattr(d, 'rssi', None)}")
    return devices


async def inspect(device) -> None:
    print(f"\n连接 {device.name!r} ({device.address}) ...")
    async with BleakClient(device, timeout=15.0) as client:
        print(f"已连接: {client.is_connected}")
        writable = []
        for service in client.services:
            print(f"\n服务 {service.uuid}  {service.description}")
            for char in service.characteristics:
                props = list(char.properties)
                value = None
                print(f"  特征 {char.uuid}  {char.description}")
                print(f"    属性: {', '.join(props)}")
                if "read" in props:
                    try:
                        value = fmt_value(await client.read_gatt_char(char))
                        print(f"    当前值: {value}")
                    except Exception as exc:
                        print(f"    读取失败: {exc}")
                        value = f"ERROR: {exc}"
                if any("write" in p for p in props):
                    writable.append((service.uuid, char.uuid, props, value))
                for desc in char.descriptors:
                    try:
                        dval = fmt_value(await client.read_gatt_descriptor(desc.handle))
                    except Exception as exc:
                        dval = f"ERROR: {exc}"
                    print(f"    描述符 {desc.uuid} {desc.description} = {dval}")

        print("\n===== 可写特征（可能用于修改灯带参数）=====")
        for svc_uuid, char_uuid, props, value in writable:
            print(f"服务 {svc_uuid} / 特征 {char_uuid} / 属性 {props} / 当前值 {value}")


async def main():
    devices = await scan()
    target = next(
        (d for d in devices if d.name and d.name.strip().upper() == "THUNDEROBOT L2"),
        None,
    )
    if target is None:
        print("\n未发现名为 THUNDEROBOT L2 的设备。请确认设备已开机并处于广播/可发现状态。")
        return
    await inspect(target)


if __name__ == "__main__":
    asyncio.run(main())
