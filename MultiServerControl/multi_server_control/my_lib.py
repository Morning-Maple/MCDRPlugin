import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import time

from mcdreforged.api.all import *
from . import default_config

"""
!!msc                       - 命令前缀
!!msc help                  - 命令帮助
!!msc list                  - 可选服务器列表
!!msc reload                - 刷新配置文件
!!msc <server_name> sync    - 对目标服务器与主服进行同步
!!msc <server_name> start   - 启动目标服务器
!!msc <server_name> stop    - 关闭目标服务器
!!msc <server_name> show    - 查看目标服务器信息
!!msc <server_name> status  - 查看目标服务器状态（正在运行/已关闭）
"""

# 控制台实例
InterFace = None
# 同步标志
syncFlag = False
# 配置文件内容
config = None
# 服务器已配置列表
server_list = []
# 插件权限等级
plugin_level = {}
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


def GetPermissionLevel(server: PluginServerInterface, source: CommandContext, only_level=False, level=0, show_warning=True):
    """
    权限检测
    :param server:
    :param source: 命令源
    :param only_level: 是否只返回等级
    :param level: 需要比较的等级
    :param show_warning: 是否展示警告
    :return: 0到4，如果only_level为True，否则会与level进行比较，只有source的权限大于等于level才返回True
    """
    target = source.source
    if target.is_console:
        return True
    if only_level:
        return target.get_permission_level()

    if target.has_permission(level):
        return True
    else:
        if show_warning:
            server.reply(f"权限不足，此命令要求等级{level}，而你只有等级{target.get_permission_level()}")
        return False


def LoadConfig():
    """
    配置文件加载函数
    :return:
    """
    print('[MSC] 加载配置文件......')
    global config, server_list, plugin_level
    with open("./config/MultiServerControl.json", "r", encoding="utf-8") as file:
        config = json.load(file)
    server_list = config.get("server_list", [])
    plugin_level = config.get("perm", {})
    print('[MSC] 加载完毕')


def CreateConfig():
    """
    配置文件创建函数
    :return:
    """
    print('[MSC] 创建配置文件中......')
    with open("./config/MultiServerControl.json", "w", encoding="utf-8") as ff:
        json.dump(default_config.DEFAULT_CONFIG, ff, indent=4, ensure_ascii=False)
    print('[MSC] 成功创建配置文件!')
    LoadConfig()


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
        server.reply(f"§c{server_name}§f不在已配置的服务器中，已配置的服务器有：§6{'，'.join(server_list)}")
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


def DisplayHelp(server: PluginServerInterface, source: CommandContext):
    """
    显示帮助信息
    :param server:
    :param source: 命令源
    :return:
    """
    global plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("help")):
        return
    for line in default_config.HELP_MSG.splitlines():
        server.reply(line)


def DisplayList(server: PluginServerInterface, source: CommandContext):
    """
    展示已配置的服务器名字
    :param server:
    :param source: 命令源
    :return:
    """
    global server_list, plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("list")):
        return
    server.reply(f"§b[MSC] §e当前已配置的服务器有：§6§l{'，'.join(server_list)}")


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

    # 检查，有就删掉再覆盖
    if os.path.exists(f'{config[server_name]["target"]}/world'):
        shutil.rmtree(f'{config[server_name]["target"]}/world/')

    # 同步
    shutil.copytree(
        f'{config[server_name]["source"]}/world',
        f'{config[server_name]["target"]}/world',
        ignore=shutil.ignore_patterns(*ignore, "session.lock")
    )

    end_time = datetime.datetime.now()
    InterFace.execute(f"say §b[MSC] §2已同步至§6§l{server_name}服务器！用时§a{end_time - start_time}")
    syncFlag = False


def Sync(server: PluginServerInterface, source: CommandContext):
    """
    服务器同步检查
    :param server:
    :param source: 命令源
    :return:
    """
    global InterFace, syncFlag, server_list, config, plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("sync")):
        return

    server_name = source["server_name"]
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    InterFace = GetInterFace()
    # 检查此名字下的服务器是否被运行同步
    can_sync = config[server_name]["can_sync"]
    if not can_sync:
        InterFace.execute(
            f"say §b[MSC] §6{server_name}§f被设置为§c不允许同步§r！！"
        )
        return

    if syncFlag:
        InterFace.execute("say §b[MSC] §e同步中，请勿重复提交同步任务！")
    else:
        InterFace.execute(f"say §b[MSC] §d正在同步到§6§l{server_name}§d服务器中......")
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
    global MirrorProcess, path
    try:
        if platform == 'win32':
            MirrorProcess = subprocess.Popen(MCDR_Command, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            MirrorProcess = subprocess.Popen(MCDR_Command, shell=True)
    except Exception as e:
        InterFace.execute(f'say §b[MSC] §4执行启动命令启动失败！原因为：§c{e}')
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
    server_path_name = server_name[0].upper() + server_name[1:]
    try:
        # 跳转到目标文件夹下
        os.chdir(server_path_name)
        CommandExecute(InterFace)
        time.sleep(5)
        os.chdir(path)
    except Exception as e:
        InterFace.execute(
            f'say §b[MSC] §4启动服务器§6§l{server_name}§4失败！原因为：§c{format(e)}'
        )


def Start(server: PluginServerInterface, source: CommandContext):
    """
    服务器启动函数
    :param server:
    :param source: 命令源
    :return:
    """
    global InterFace, syncFlag, plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("start")):
        return

    server_name = source["server_name"]
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return
    InterFace = GetInterFace()
    if syncFlag:
        InterFace.execute(f'say §b[MSC] §6§l{server_name}正在进行同步，请稍后再启动')
    else:
        InterFace.execute(f'say §b[MSC] §a正在启动§6§l{server_name}§a服务器，请稍等……')
        ServerStart(InterFace, server_name)
        time.sleep(default_config.START_WAIT_TIME)
        InterFace.execute(
            f'say §b[MSC] §6§l{server_name}§a启动命令已执行，完全启动后请使用§6§l/server {server_name} §a进行连接§e（需装Velocity）')


def Stop(server: PluginServerInterface, source: CommandContext):
    """
    服务器停止函数，需要开启rcon才可使用
    :param server:
    :param source: 命令源
    :return:
    """
    global InterFace, plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("stop")):
        return

    server_name = source["server_name"]
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    InterFace = GetInterFace()

    if config[server_name]['rcon']['enable']:
        conn = RconInit(server_name)
        try:
            connected = conn.connect()
            if connected:
                conn.send_command('stop', max_retry_time=3)
                conn.disconnect()
                InterFace.execute(f'say §b[MSC] §6§l{server_name}§a服务器已执行关闭命令……')
        except Exception as e:
            InterFace.execute(f'say §b[MSC] §4无法执行命令关闭服务器：§6§l{server_name}§4，原因为：§c{format(e)}')
    else:
        InterFace.execute(f'say §b[MSC] §4无法通过§6§lRcon§4关闭§6§l{server_name}§4服务器，因为§6§l{server_name}服务器的§6§lRcon未开启！')


def Status(server: PluginServerInterface, source: CommandContext, is_show=True):
    """
    查询服务器状态（通过检查端口是否被占用）
    :param server:
    :param source: 命令源
    :param is_show: 是否输出到游戏内（默认True）
    :return:
    """
    global plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("status")):
        return

    server_name = source["server_name"]
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    port = config[server_name]["port"]
    host = config[server_name]["rcon"]["host"]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            if is_show:
                server.reply(f'§b[MSC] §f服务器§6§l{server_name}§f的状态为：§c关闭')
            return False
        except OSError:
            if is_show:
                server.reply(f'§b[MSC] §f服务器§6§l{server_name}§f的状态为：§a正在运行')
            return True


def Show(server: PluginServerInterface, source: CommandContext):
    """
    展示目标服务器信息
    :param server:
    :param source: 命令源
    :return:
    """
    global plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("show")):
        return

    server_name = source["server_name"]
    # 检查名字是否在配置单中
    if not ServerNameCheck(server, server_name):
        return

    server.reply("================")
    server.reply(f"§6§l{server_name}服务器信息如下：")
    server.reply(f"描述：§e{config[server_name]['description']}")

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

    Status(server, source, True)


def Reload(server: PluginServerInterface, source: CommandContext):
    """
    重新读取插件配置文件
    :param server:
    :param source: 命令源
    :return:
    """
    global plugin_level
    # 权限校验
    if not GetPermissionLevel(server, source, level=plugin_level.get("reload")):
        return

    server.reply('§b[MSC] §2正在重载配置文件……')
    ConfigToDo()
    server.reply('§b[MSC] §a重载完成！')


def register(server: PluginServerInterface):
    """
    插件注册
    :param server:
    :return:
    """
    ConfigToDo()
    print(server_list)
    server.register_help_message("!!msc", "MultiServerControl 帮助")
    builder = SimpleCommandBuilder()
    builder.command("!!msc", DisplayHelp)
    builder.command("!!msc help", DisplayHelp)
    builder.command("!!msc list", DisplayList)
    builder.command("!!msc reload", Reload)
    builder.command("!!msc sync <server_name>", Sync)
    builder.command("!!msc start <server_name>", Start)
    builder.command("!!msc stop <server_name>", Stop)
    builder.command("!!msc show <server_name>", Show)
    builder.command("!!msc status <server_name>", Status)
    builder.arg("server_name", Text).suggests(lambda: ['mirror', 'create'])
    builder.register(server)
