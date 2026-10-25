import mcdreforged as mcdr

from . import my_lib


def on_load(server: mcdr.PluginServerInterface, old):
    """
    插件加载时需要干的工作
    :param server: 本次实例
    :param old: 该模块上一次的实例
    """
    server.logger.info('[AdvMaple] 插件已加载')
    my_lib.register(server)


def on_player_joined(server: mcdr.PluginServerInterface, player: str, info):
    """玩家加入时登记到在线集合 (!!madv sync 全服同步与补全都依赖它)"""
    my_lib.mark_player_online(player)


def on_player_left(server: mcdr.PluginServerInterface, player: str):
    """玩家离线时移出在线集合"""
    my_lib.mark_player_offline(player)


def on_unload(server: mcdr.PluginServerInterface):
    """
    插件被卸载的时候需要干的工作
    :param server: 本次实例
    """
    server.logger.info('[AdvMaple] 插件已被卸载')
