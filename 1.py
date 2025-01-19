import asyncio
import io
import json
import math
import qrcode
import socket
from aiohttp import web
import winreg
import os
from pydglab_ws import (
    FeedbackButton,
    Channel,
    RetCode,
    DGLabWSServer,
    StrengthOperationType,
    StrengthData,
)
import tkinter as tk
from PIL import Image, ImageTk
from multiprocessing import Process, Queue


# 读取 PULSE_DATA 从 JSON 文件
with open("config.json", "r", encoding="utf-8") as file:
    config = json.load(file)
    PULSE_DATA = config["pulse_data"]
    HIT = config["hit"]


def get_ip_address():
    """获取本机IP地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()
    ip_address = f"ws://{ip_address}:5678"
    return ip_address


csi = None
def script_load():
    global csi_path

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\Valve\Steam', 0, winreg.KEY_READ)
        path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
    except:
        return None

    libpath = path + '/steamapps/libraryfolders.vdf'

    with open(libpath, 'r') as libvdf:
        library = libvdf.readlines()
        last_path = None
        found = False

        for line in library:
            pair = line.strip('\n').strip('\t')
            if pair.startswith('"path"'):
                _, v = pair.split('\t\t')
                last_path = v.strip('"').encode().decode('unicode_escape')
            elif '"730"' in pair:
                found = True
                break

        if found and os.path.exists(last_path + '\\steamapps\\common\\Counter-Strike Global Offensive\\'):
            csi_path = last_path + '\\steamapps\\common\\Counter-Strike Global Offensive\\'
        print(f"已找到 CS2 安装路径: {csi_path}")


# def get_cs2_path():
#     try:
#         key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\steam")
#         steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
#         print("已找到 Steam 安装路径: " + steam_path)
#         winreg.CloseKey(key)
#         cs2_path = steam_path + r"\steamapps\common\Counter-Strike Global Offensive"
#         return cs2_path
#     except FileNotFoundError:
#         print("未找到 Steam 注册表项")
#         return None
#     except Exception as e:
#         print(f"读取注册表时发生错误: {e}")
#         return None


def auto_set_cfg():
    cfg = """"CS2&DGLAB"
{
 "uri" "http://127.0.0.1:3000"
 "timeout" "0.1"
 "buffer"  "0.1"
 "throttle" "0.5"
 "heartbeat" "1.0"
 "auth"
 {
   "token" "MYTOKENHERE"
 }
 "data"
 {
   "provider"            "1"
   "map"                 "1"
   "round"               "1"
   "player_id"           "1"
   "player_state"        "1"
 }
}
"""
    try:
        script_load()
        if os.path.exists(csi_path + 'csgo\\cfg'):
            with open(csi_path + 'csgo\\cfg\\gamestate_integration_nodecs2.cfg', 'w') as fd:
                fd.write(cfg)

        if os.path.exists(csi_path + 'game\\csgo\\cfg'):
            with open(csi_path + 'game\\csgo\\cfg\\gamestate_integration_nodecs2.cfg', 'w') as fd:
                fd.write(cfg)
    except Exception as e:
        print(f"写入文件时发生错误: {e}")
        return False
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
    img_path = "temp_qrcode1.png"
    img.save(img_path)
    return img_path


def read_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as file:
            config_data = json.load(file)
            # 处理config_data，例如打印每个字段的信息
            for key, value in config_data.items():
                print(f"{key}: {value}")
    except FileNotFoundError:
        print("config.json文件未找到")
    except json.JSONDecodeError:
        print("config.json文件格式错误")


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
                    data_a = math.ceil((100 - now_health) / 100 * max_strength_A*(HIT/100))
                    data_b = math.ceil((100 - now_health) / 100 * max_strength_B*(HIT/100))
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
                # 血量归零以及回合结束重置强度以及血量
                if now_health == 0:
                    waveform_data = {"type": "pluse", "data": PULSE_DATA["死亡"]}
                    await queue.put(waveform_data)
                    await asyncio.sleep(5)
                    waveform_data = {"type": "strlse", "data": 100}
                    await queue.put(waveform_data)
                    health = 100
                if "round" in data:
                    if data["round"]["phase"] == "over":
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
    global max_strength_A, max_strength_B, strenghth_A, strenghth_B
    queue = asyncio.Queue()

    app = web.Application()
    app["queue"] = queue
    app.router.add_post("/", handle_post_request)

    async with DGLabWSServer("0.0.0.0", 5678, 60) as server:
        client = server.new_local_client()
        ip_path = get_ip_address()
        print("获取到本地IP地址：" + ip_path)
        if auto_set_cfg():
            print("自动导入cfg成功")
        url = client.get_qrcode(ip_path)
        print("请用 DG-Lab App 扫描二维码以连接")
        print_qrcode(url)
        # 创建进程间通信的队列
        gui_queue = Queue()
        # 启动GUI进程
        gui_process = Process(target=start_gui, args=(strenghth_A, strenghth_B, gui_queue))
        gui_process.start()

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

        async for data in client.data_generator():
            # 接收通道强度数据
            if isinstance(data, StrengthData):
                max_strength_A = data.a_limit
                max_strength_B = data.b_limit
                strenghth_A = data.a
                strenghth_B = data.b
                # 将更新的数据发送到 GUI 进程
                gui_queue.put((strenghth_A, strenghth_B))
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


def start_gui(strength_A, strength_B, gui_queue):
    # 声明 hit_field 为全局变量
    global hit_field

    def update_hit_field():
        try:
            with open('config.json', 'r', encoding='utf-8') as file:
                config_data = json.load(file)
                hit_value = config_data.get('hit', '')
                # 这里使用全局变量 hit_field
                hit_field.delete(1.0, tk.END)
                hit_field.insert(tk.END, hit_value)
        except Exception as e:
            print(f"读取 config.json 出错: {e}")

    def save_hit_field():
        try:
            with open('config.json', 'r+', encoding='utf-8') as file:
                config_data = json.load(file)
                new_hit_value = hit_field.get(1.0, tk.END).strip()
                config_data['hit'] = new_hit_value
                global HIT
                HIT = new_hit_value
                file.seek(0)
                json.dump(config_data, file, indent=4)
                file.truncate()
        except Exception as e:
            print(f"保存 config.json 出错: {e}")

    root = tk.Tk()
    root.title("CS2&郊狼")
    root.geometry("400x400")  # 设置窗口大小
    sidebar_frame = tk.Frame(root, width=200, bg='light grey')
    sidebar_frame.grid(row=0, column=0, sticky="nsew")
    data_button = tk.Button(sidebar_frame, text="显示数据", bd=0, anchor=tk.W, command=lambda: show_section('data'))
    data_button.pack(pady=10, padx=10, fill=tk.X)
    event_button = tk.Button(sidebar_frame, text="功能", bd=0, anchor=tk.W, command=lambda: show_section('hit'))
    event_button.pack(pady=10, padx=10, fill=tk.X)
    main_frame = tk.Frame(root)
    main_frame.grid(row=0, column=1, sticky="nsew")
    root.grid_rowconfigure(0, weight=5)
    root.grid_columnconfigure(1, weight=1)

    # 显示通道强度A的标签
    strength_a_label = tk.Label(main_frame, text=f"通道强度A: {strength_A}")
    strength_a_label.pack()

    # 显示通道强度B的标签
    strength_b_label = tk.Label(main_frame, text=f"通道强度B: {strength_B}")
    strength_b_label.pack()

    def update_strength_labels():
        try:
            new_strength_A, new_strength_B = gui_queue.get_nowait()
            strength_a_label.config(text=f"通道强度A: {new_strength_A}")
            strength_b_label.config(text=f"通道强度B: {new_strength_B}")
        except Exception:
            pass
        root.after(100, update_strength_labels)

    def show_qrcode():
        img_path = "temp_qrcode1.png"
        img = Image.open(img_path)
        # 调整图像显示尺寸和质量
        img = img.resize((300, 300), Image.LANCZOS)
        img = ImageTk.PhotoImage(img)
        if hasattr(show_qrcode, 'qrcode_label'):
            show_qrcode.qrcode_label.config(image=img)
            show_qrcode.qrcode_label.image = img
            show_qrcode.qrcode_label.pack()  # 确保标签显示
        else:
            qrcode_label = tk.Label(main_frame, image=img)
            qrcode_label.image = img
            qrcode_label.pack()
            show_qrcode.qrcode_label = qrcode_label

    # 显示二维码的按钮
    qrcode_button = tk.Button(main_frame, text="显示二维码", command=show_qrcode)
    qrcode_button.pack()

    def create_hit_textbox():
        if hasattr(create_hit_textbox, 'hit_frame'):
            # 如果存在，显示现有的输入框
            create_hit_textbox.hit_frame.pack(pady=10)
        else:
            # 否则创建新的输入框
            hit_frame = tk.Frame(main_frame)
            hit_frame.pack(pady=10)
            
            create_hit_textbox.hit_frame = hit_frame

            hit_label = tk.Label(hit_frame, text="血量强度衰减（原为100%）:")
            hit_label.pack(side=tk.TOP)

            global hit_field
            hit_field = tk.Text(hit_frame, height=5, width=30)
            hit_field.pack(side=tk.TOP)
            update_hit_field()

            save_button = tk.Button(hit_frame, text="保存", command=save_hit_field)
            save_button.pack(side=tk.TOP)

    def show_section(section):
        # 隐藏所有组件
        strength_a_label.pack_forget()
        strength_b_label.pack_forget()
        qrcode_button.pack_forget()
        if hasattr(create_hit_textbox, 'hit_frame'):
            create_hit_textbox.hit_frame.pack_forget()
        if hasattr(show_qrcode, 'qrcode_label'):
            show_qrcode.qrcode_label.pack_forget()

        if section == 'data':
            # 显示通道强度和二维码按钮
            strength_a_label.pack()
            strength_b_label.pack()
            qrcode_button.pack()
            show_qrcode()  # 显示二维码
        elif section == 'hit':
            # 显示血量强度衰减选项
            create_hit_textbox()

    update_strength_labels()
    root.mainloop()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    asyncio.run(main())