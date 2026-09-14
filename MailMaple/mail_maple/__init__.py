import mcdreforged as mcdr

from . import mail_lib


def on_load(server: mcdr.PluginServerInterface, old):
    """
    插件加载: 注册命令、加载配置、初始化真人注册表
    :param server: 本次实例
    :param old: 该模块上一次的实例
    """
    server.logger.info('[MailMaple] 插件已加载')
    mail_lib.register(server)


def on_player_joined(server: mcdr.PluginServerInterface, player: str, info):
    """
    玩家上线: 标记在线 + 记录真人到注册表 (过滤假人), 并提示未读邮件
    :param server: 本次实例
    :param player: 上线玩家名
    :param info: 对应的 Info 实例
    """
    mail_lib.mark_player_online(player)
    mail_lib.on_player_joined(player)


def on_player_left(server: mcdr.PluginServerInterface, player: str):
    """
    玩家离线: 从在线集合移除
    :param server: 本次实例
    :param player: 离线玩家名
    """
    mail_lib.mark_player_offline(player)


def on_unload(server: mcdr.PluginServerInterface):
    """
    插件卸载: 持久化数据
    :param server: 本次实例
    """
    mail_lib.on_unload()
    server.logger.info('[MailMaple] 插件已被卸载')
