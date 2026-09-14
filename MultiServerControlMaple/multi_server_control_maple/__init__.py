"""
__init__.py — MultiServerControlMaple 事件入口

MCDR 在对应事件触发时调用本模块的同名函数, 实际逻辑下放到 my_lib / commands。
具体的多子服控制流程 (列出子服、启动/关闭子服、与主服同步存档、查询子服状态等)
将在需求确认后补全, 此处仅搭好骨架与挂载点。
"""
import mcdreforged as mcdr

from . import my_lib


def on_load(server: mcdr.PluginServerInterface, old):
    """
    插件加载: 注册命令、加载配置、初始化运行时状态
    :param server: 本次实例
    :param old: 该模块上一次的实例
    """
    server.logger.info('[MultiServerControlMaple] 插件已加载')
    my_lib.register(server)


def on_unload(server: mcdr.PluginServerInterface):
    """
    插件卸载: 持久化数据 / 清理运行时状态
    :param server: 本次实例
    """
    my_lib.on_unload()
    server.logger.info('[MultiServerControlMaple] 插件已被卸载')
