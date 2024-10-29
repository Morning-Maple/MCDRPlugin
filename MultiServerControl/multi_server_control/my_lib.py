import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import time

from mcdreforged.api.all import *

"""
Literal('!!msc')                - 命令前缀
 ├─ Literal('help')             - 命令帮助
 ├─ Literal('list')             - 可选服务器列表
 ├─ Literal('reload')           - 刷新配置文件
 └─ Literal('server')           - 匹配服务器
     └─ Text('server_name')       选择服务器名字
         ├─ Literal('sync')     - 对目标服务器与主服进行同步
         ├─ Literal('start')    - 启动目标服务器
         ├─ Literal('stop')     - 关闭目标服务器
         ├─ Literal('show')     - 查看目标服务器信息
         └─ Literal('status')   - 查看目标服务器状态（正在运行/已关闭）
"""

# 读插件元数据
with open("../mcdreforged.plugin.json", "r", encoding="utf-8") as f:
    PLUGIN_METADATA = json.load(f)

# 默认帮助信息
help_msg = '''{:=^50}
§b!!msc §r- §6显示帮助信息
§b!!msc help §r- §6显示帮助信息
§b!!msc list §r- §6显示在册的服务器名字
§b!!msc reload §r- §6重新载入配置
§b!!msc <server_name> sync §r- §6对名为server_name的服务器进行同步
§b!!msc <server_name> start §r- §6启动名为server_name的服务器
§b!!msc <server_name> stop §r- §6关闭名为server_name的服务器（需要开启Rcon）
§b!!msc <server_name> show §r- §6查看名为server_name的服务器信息
§b!!msc <server_name> status §r- §6查询名为server_name的服务器的状态（正在运行/已关闭）
{:=^50}''' \
    .format(' §b[MultiServerControl] 帮助信息 §r',
            ' §b[MultiServerControl] Version: {} §r'
            .format(PLUGIN_METADATA["version"]))

# 本机地址
host = "localhost"
# 控制台实例
InterFace = None
# 同步标志
syncFlag = False
# 配置文件内容
config = None
# 服务器已配置列表
server_list = []
# 插件所在路径与环境
path = os.getcwd()
platform = sys.platform
# 镜像线程
MirrorProcess = None

# 启动命令
if platform == "win32":
    MCDR_Command = "python -m mcdreforged"
else:
    MCDR_Command = 'python3 -m mcdreforged'


def LoadConfig():
    """
    配置文件加载函数
    :return:
    """
    print('[MSC] 加载配置文件中......')
    global config, server_list
    with open("./config/MultiServerControl.json", "r", encoding="utf-8") as file:
        config = json.load(file)
    server_list = config.get("server_list", [])


def CreateConfig():
    """
    配置文件创建函数
    :return:
    """
    print('[MSC] 创建配置文件中......')
    shutil.copy("default_config.json", "./config/MultiServerControl.json")


def ConfigToDo():
    """
    初始化配置文件
    :return: None
    """
    if os.path.exists('./config/MultiServerControl.json'):
        LoadConfig()
    else:
        CreateConfig()


def ServerNameCheck(server: PluginServerInterface, server_name):
    """
    检查服务器名字是否在配置单中
    :param server:
    :param server_name: 服务器名字
    :return:
    """
    if server_name not in server_list:
        server.reply(f"{server_name}不在已配置的服务器中，已配置的服务器有：{server_list}")
        return False
    return True


def GetInterFace(*args):
    """
    获取并返回服务器实例
    :param args:
    :return:
    """
    global InterFace
    InterFace = ServerInterface.get_instance().as_plugin_server_interface()
    return InterFace


def RconInit(server_name):
    """
    创建Rcon客户端实例
    :param server_name: 服务器名字
    :return:
    """
    global config
    rcon = config[server_name]["rcon"]
    Rcon = RconConnection(rcon["host"], rcon["port"], rcon["password"])
    return Rcon


def DisplayHelp(server: PluginServerInterface):
    """
    显示帮助信息
    :param server:
    :return:
    """
    for line in help_msg.splitlines():
        server.reply(line)


def DisplayList(server: PluginServerInterface):
    """
    展示已配置的服务器名字
    :param server:
    :return:
    """
    global InterFace, config, server_list
    InterFace = GetInterFace()
    InterFace.execute(
        f"say §b[MSC] §e当前已配置的服务器有：{server_list}"
    )


@new_thread("MSC-Sync")
def ServerSync(InterFace, server_name):
    """
    同步镜像服的内容
    :param InterFace:
    :param server_name: 目标服务器名字
    :return:
    """
    global syncFlag, config
    syncFlag = True
    start_time = datetime.datetime.now()

    # 需要忽略的文件
    ignore = config[server_name].get("ignore_files", [])

    shutil.copytree(
        config[server_name]["source"],
        config[server_name]["target"],
        ignore=shutil.ignore_patterns(*ignore, "session.lock")
    )

    end_time = datetime.datetime.now()
    InterFace.execute(
        f"say §b[MSC] §6同步完成！用时{end_time - start_time}"
    )
    syncFlag = False


def Sync(server: PluginServerInterface, server_name):
    """
    服务器同步检查
    :param server:
    :param server_name: 目标服务器名字
    :return:
    """
    global InterFace, syncFlag, server_list, config
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    # 检查此名字下的服务器是否被运行同步
    can_sync = config[server_name]["can_sync"]
    if not can_sync:
        server.reply(f"{server_name}被设置为不允许同步！")
        return

    InterFace = GetInterFace()
    if syncFlag:
        InterFace.execute(
            "say §b[MSC] §d同步中，请勿重复提交同步任务！"
        )
    else:
        InterFace.execute("say §b[MSC] §d正在同步到镜像服务器中......")
        InterFace.execute('save-off')
        InterFace.execute('save-all')
        ServerSync(InterFace, server_name)
        InterFace.execute('save-on')


@new_thread("MSC-Start")
def CommandExecute(InterFace):
    """
    服务器执行启动命令函数
    :param InterFace:
    :return:
    """
    global MirrorProcess
    try:
        if platform == 'win32':
            MirrorProcess = subprocess.Popen(MCDR_Command, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            MirrorProcess = subprocess.Popen(MCDR_Command, shell=True)
    except Exception as e:
        InterFace.execute(f'say §b[MSC] §6启动失败！原因为：{e}')
    os.chdir(path)


@new_thread("MSC-Main")
def ServerStart(InterFace, server_name):
    """
    文件夹跳转函数
    :param InterFace:
    :param server_name: 目标服务器名字
    :return:
    """
    global path
    try:
        # 跳转到目标文件夹下
        os.chdir(server_name)
        CommandExecute(InterFace)
        time.sleep(5)
        os.chdir(path)
    except Exception as e:
        InterFace.execute(
            'say §b[MSC] §6启动失败！原因为：{}'.format(e)
        )


def Start(server: PluginServerInterface, server_name):
    """
    服务器启动函数
    :param server:
    :param server_name:
    :return:
    """
    global InterFace, syncFlag
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return
    InterFace = GetInterFace()
    if syncFlag:
        InterFace.execute(f'say §b[MSC] §d§l{server_name}正在进行同步，请稍后再启动')
    else:
        InterFace.execute(f'say §b[MSC] §6正在启动{server_name}服务器，请稍等……')
        ServerStart(InterFace, server_name)
        InterFace.execute(f'say §b[MSC] §6{server_name}启动完成，请使用/server {server_name} 进行连接')


def Stop(server: PluginServerInterface, server_name):
    """
    服务器停止函数，需要开启rcon才可使用
    :param server:
    :param server_name: 目标服务器名字
    :return:
    """
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return
    if config[server_name]['rcon']['enable']:
        conn = RconInit(server_name)
        try:
            connected = conn.connect()
            if connected:
                conn.send_command('stop', max_retry_time=3)
                conn.disconnect()
        except Exception as e:
            server.reply(f'§b[MSC] §6无法停止{server_name}服务器！原因为：{format(e)}')
    else:
        server.reply(f'§b[MSC] §6无法通过Rcon停止镜像服，因为{server_name}服务器的Rcon未开启！')


def Status(server: PluginServerInterface, server_name, is_show=False):
    """
    查询服务器状态（通过检查端口是否被占用）
    :param server:
    :param server_name: 目标服务器名字
    :param is_show: 是否输出到游戏内（默认False）
    :return:
    """
    global host
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    port = config[server_name]["port"]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            if is_show:
                server.reply(f'§b[MSC] 服务器§e{server_name}的状态为：§c关闭')
            return False
        except OSError:
            if is_show:
                server.reply(f'§b[MSC] 服务器§e{server_name}的状态为：§a正在运行')
            return True


def Show(server: PluginServerInterface, server_name):
    """
    展示目标服务器信息
    :param server:
    :param server_name: 目标服务器名字
    :return:
    """
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    server.reply(f"§e{server_name}信息如下：")
    server.reply(f"描述：{config[server_name]['description']}")

    if config[server_name]['can_sync'] is True:
        server.reply("是否允许被同步：§2是")
    elif config[server_name]['can_sync'] is False:
        server.reply("是否允许被同步：§c否")
    else:
        server.reply("是否允许被同步：§d未知")

    if config[server_name]['rcon']['enable'] is True:
        server.reply("Rcon启用情况：§2已启用")
    elif config[server_name]['rcon']['enable'] is False:
        server.reply("Rcon启用情况：§c未启用")
    else:
        server.reply("Rcon启用情况：§d未知")

    Status(server, server_name, True)


def Reload(server: PluginServerInterface):
    """
    重新读取插件配置文件
    :param server:
    :return:
    """
    server.reply('§b[MirrorServerReforged] §6正在重载配置文件……')
    ConfigToDo()
    server.reply('§b[MirrorServerReforged] §6重载完成！')


def register(server: PluginServerInterface):
    """
    插件注册
    :param server:
    :return:
    """
    server.register_help_message("!!msc", "MultiServerControl 帮助")
    server.register_command(
        Literal('!!msc')
        .runs(DisplayHelp)
        .then(
            Text("args")
            .suggests(lambda: ["help", "list", "server"])
            .then(
                Literal("help")
                .runs(DisplayHelp)
            )
            .then(
                Literal("list")
                .runs(DisplayList)
            )
            .then(
                Literal("reload")
                .runs(Reload)
            )
            .then(
                Literal("server")
                .then(
                    Text("server_name")
                    .suggests(lambda: server_list)
                )
                .suggests(lambda: ["sync", "start", "stop", "show", "status"])
                .then(
                    Literal("sync")
                    .runs(Sync)
                )
                .then(
                    Literal("start")
                    .runs(Start)
                )
                .then(
                    Literal("stop")
                    .runs(Stop)
                )
                .then(
                    Literal("show")
                    .runs(Show)
                )
                .then(
                    Literal("status")
                    .runs(Status)
                )
            )
        )
    )
