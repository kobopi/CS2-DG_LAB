import asyncio
import io
import json
import math
import wx
import qrcode
from aiohttp import web
from pydglab_ws import (
    FeedbackButton,
    Channel,
    RetCode,
    DGLabWSServer,
    StrengthOperationType,
    StrengthData,
)

# 读取 PULSE_DATA 从 JSON 文件
with open('config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)
    PULSE_DATA = config['pulse_data']
    ip_path = config['ip_path']
def print_qrcode(data: str):
    """输出二维码到终端界面"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    f = io.StringIO()
    img = qr.make_image(fill_color="black", back_color="white")
    img_path = "temp_qrcode.png"
    img.save(img_path)



health = 100
max_strength_A = 0
max_strength_B = 0
strenghth_A = 0
strenghth_B = 0


async def handle_post_request(request):
    global health
    queue = request.app["queue"]  # 从app中获取queue
    """处理cs数据请求请求"""
    try:
        data = await request.json()
        if not data:
            return web.json_response(
                {"status": "error", "message": "请求体为空"}, status=400
            )
        if "player" in data and "map" in data:
            if data["provider"]["steamid"] == data["player"]["steamid"]:
                now_health = data["player"]["state"]["health"]
                flash = data["player"]["state"]["flashed"]
                somke = data["player"]["state"]["smoked"]
                # 血量减少（调整强度，发送波形）
                if now_health < health:
                    data_a = math.ceil((100 - now_health) / 100 * max_strength_A)
                    data_b = math.ceil((100 - now_health) / 100 * max_strength_B)
                    print(f"玩家生命值减少: {health} -> {now_health}")
                    # 这里多写一层判断，判断是否被烧伤
                    if data["player"]["state"]["burning"] > 0:
                        waveform_data = {"type": "pluse", "data": PULSE_DATA["烧伤"]}
                        await queue.put(waveform_data)
                    else:
                        waveform_data = {"type": "pluse", "data": PULSE_DATA["受伤"]}
                        await queue.put(waveform_data)
                    # 强度
                    waveform_data = {
                        "type": "strlup",
                        "data": strenghth_A - data_a,
                        "chose": "a",
                    }
                    await queue.put(waveform_data)
                    waveform_data = {
                        "type": "strlup",
                        "data": strenghth_B - data_b,
                        "chose": "b",
                    }
                    await queue.put(waveform_data)
                    health = now_health
                # 傻瓜蛋！
                if flash > 0:
                    waveform_data = {"type": "pluse", "data": PULSE_DATA["傻瓜蛋"]}
                    await queue.put(waveform_data)
                if somke > 0:
                    waveform_data = {"type": "pluse", "data": PULSE_DATA["烟雾弹"]}
                    await queue.put(waveform_data)
                # 血量归零重置强度以及血量
                if now_health == 0:
                    health = 100
                    waveform_data = {"type": "pluse", "data": PULSE_DATA["死亡"]}
                    await queue.put(waveform_data)
                    await asyncio.sleep(5)
                    waveform_data = {"type": "strlse", "data": 100}
                    await queue.put(waveform_data)
                # 游戏结束重置强度
                if data["map"]["phase"] == "gameover":
                    waveform_data = {"type": "strlse", "data": 100}
                    await queue.put(waveform_data)
                return web.json_response({"status": "success", "message": "数据已接收"})
    except Exception as e:
        print(f"处理POST请求时出错: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def send_waveform_on_queue_change(queue, client):
    while True:
        waveform_data = await queue.get()
        types = waveform_data["type"]
        data = waveform_data["data"]
        if types == "pluse":
            await client.add_pulses(Channel.A, *(data * 1))
            await client.add_pulses(Channel.B, *(data * 1))
        elif types == "strlup":
            chose = waveform_data["chose"]
            if chose == "a":
                await client.set_strength(
                    Channel.A, StrengthOperationType.INCREASE, data
                )
            if chose == "b":
                await client.set_strength(
                    Channel.B, StrengthOperationType.INCREASE, data
                )
        elif types == "strlse":
            await client.set_strength(Channel.A, StrengthOperationType.DECREASE, 200)
            await client.set_strength(Channel.B, StrengthOperationType.DECREASE, 200)
        elif types == "strlst":
            await client.set_strength(Channel.A, StrengthOperationType.SET_TO, data)
            await client.set_strength(Channel.B, StrengthOperationType.SET_TO, data)
        else:
            print("接收到未知类型数据，请检查")


async def main():
    queue = asyncio.Queue()

    app = web.Application()
    app["queue"] = queue
    app.router.add_post("/", handle_post_request)

    async with DGLabWSServer("0.0.0.0", 5678, 60) as server:
        client = server.new_local_client()

        url = client.get_qrcode(ip_path)
        print("请用 DG-Lab App 扫描文件夹中二维码以连接")
        print_qrcode(url)
        # 等待绑定
        await client.bind()
        print(f"已与 App {client.target_id} 成功绑定")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 3000)
        await site.start()
        print("HTTP服务器已启动，监听端口 3000")

        # 启动监视队列的任务
        queue_monitor_task = asyncio.create_task(
            send_waveform_on_queue_change(queue, client)
        )


        last_strength = None
        global max_strength_A, max_strength_B, strenghth_A, strenghth_B
        async for data in client.data_generator():

            # 接收通道强度数据
            if isinstance(data, StrengthData):
                max_strength_A = data.a_limit
                max_strength_B = data.b_limit
                strenghth_A = data.a
                strenghth_B = data.b
            # 接收 App 反馈按钮
            elif isinstance(data, FeedbackButton):
                print(f"App 触发了反馈按钮：{data.name}")

                if data == FeedbackButton.A1:
                    # 之后这边要写逻辑
                    print("按下 A1")

            # 接收 心跳 / App 断开通知
            elif data == RetCode.CLIENT_DISCONNECTED:
                print("App 已断开连接，你可以尝试重新扫码进行连接绑定")
                await client.rebind()
                print("重新绑定成功")

        # 确保队列监视任务在主循环结束后取消
        queue_monitor_task.cancel()
        try:
            await queue_monitor_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
