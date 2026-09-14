import mcdreforged as mcdr

from . import my_lib


def on_load(server: mcdr.PluginServerInterface, old):
    """
    插件加载时需要干的工作
    :param server: 本次实例
    :param old: 该模块上一次的实例
    """
    server.logger.info('[TpMaple] 插件已加载')
    my_lib.register(server)


def on_player_joined(server: mcdr.PluginServerInterface, player: str, info):
    """玩家加入时记录到在线集合 (用于死亡检测归属)"""
    my_lib.mark_player_online(player)


def on_player_left(server: mcdr.PluginServerInterface, player: str):
    """
    玩家离线时清理其相关的 tpa 请求 (防内存泄漏) 并移出在线集合
    :param server: 本次实例
    :param player: 离线玩家名
    """
    my_lib.mark_player_offline(player)
    from .commands import tpa as tpa_cmd
    tpa_cmd.clear_player_requests(player)


def on_info(server: mcdr.PluginServerInterface, info):
    """解析服务端输出, 检测玩家死亡并发送 back 提示"""
    my_lib.handle_info_for_death(info)


def on_unload(server: mcdr.PluginServerInterface):
    """
    插件被卸载的时候需要干的工作
    :param server: 本次实例
    """
    server.logger.info('[TpMaple] 插件已被卸载')