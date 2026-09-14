"""
show.py — !!mscm show [名字]

- !!mscm show          查看所有子服一览 (每行: 名字 / 可同步或独立 / 在线离线 / 人数)
- !!mscm show <名字>   查看指定子服详情 (含操作按钮)

在线与否、人数等通过 SLP 探测 (见 ../slp.py): 能 ping 通即「玩家可进入」=在线。
探测会阻塞至多 probe_timeout 秒, 故回调用 @new_thread; show(全部) 并发探测各子服。
"""
from concurrent.futures import ThreadPoolExecutor

import mcdreforged as mcdr
from mcdreforged.api.rtext import RText, RTextList, RColor, RAction

from .. import my_lib
from ..slp import ServerListPing, SlpStatus

TAG = my_lib.TAG


# ============================================================
# 内部工具
# ============================================================

def _server_port(cfg: dict) -> int:
    try:
        return int(cfg.get("port", 25565))
    except (TypeError, ValueError):
        return 25565


def _probe(item):
    """探测单个子服, 返回 (name, cfg, status|None)。供并发调用。"""
    name, cfg = item
    host = cfg.get("host", "127.0.0.1")
    status = ServerListPing.ping(host, _server_port(cfg), timeout=my_lib.get_probe_timeout())
    return name, cfg, status


def _count_text(status) -> str:
    """人数文本: 在线显示 x/x, 离线显示 -/-。"""
    if status is None:
        return "§7-/-§r"
    return "§a{}§r/§a{}§r".format(status.online, status.max_players)


# ============================================================
# !!mscm show  (全部)
# ============================================================

@mcdr.new_thread("MSC-show-all")
def show_all(source: mcdr.CommandSource):
    """列出所有子服的一行简介。"""
    servers = my_lib.get_servers()
    if not servers:
        source.reply(TAG + "§7当前没有配置任何子服务器，请在配置文件中添加后 §b{} §7重载".format(my_lib.cmd("reload")))
        return

    items = list(servers.items())
    # 并发探测, 保留配置顺序
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as executor:
        results = list(executor.map(_probe, items))

    source.reply(TAG + "§6子服务器列表 ({}):".format(len(results)))
    for name, cfg, status in results:
        display = cfg.get("cn_name") or name
        sync_text = "可同步" if cfg.get("can_sync", False) else "独立"
        state = "§a在线§r" if status is not None else "§c离线§r"
        source.reply(
            "§6【{name}】§b【{sync}】§r 状态：{state}；人数：{count}；".format(
                name=display, sync=sync_text, state=state, count=_count_text(status),
            )
        )


# ============================================================
# !!mscm show <名字>  (详情)
# ============================================================

@mcdr.new_thread("MSC-show-one")
def show_one(source: mcdr.CommandSource, context: dict):
    """展示指定子服详情, 含 [同步][停止/开启][重启] (暂为纯文本) 与 [连接到此服务器]。"""
    name: str = context["server_name"]
    cfg = my_lib.get_server(name)
    if cfg is None:
        source.reply(
            TAG + "§c未找到子服务器 §e{}§c，使用 §b{} §c查看可用列表".format(name, my_lib.cmd("show"))
        )
        return

    host = cfg.get("host", "127.0.0.1")
    status: SlpStatus = ServerListPing.ping(host, _server_port(cfg), timeout=my_lib.get_probe_timeout())
    online = status is not None
    can_sync = bool(cfg.get("can_sync", False))
    display = cfg.get("cn_name") or name

    source.reply("§6【{}】".format(display))
    source.reply("§7此服可同步主服；" if can_sync else "§7此服是独立服务器；")
    source.reply("状态：{}§r".format("§a在线" if online else "§c离线"))
    source.reply("人数：{}".format(_count_text(status)))
    if online and status.online > 0:
        names = "、".join(status.players) if status.players else "§7（服务器未提供名单）"
        source.reply("在线玩家：§a{}".format(names))

    # 操作按钮: 同步 / 停止或开启 / 重启 (可点击; 点击后各命令会各自弹二次确认)
    action = my_lib.get_click_action()
    buttons = []

    # [同步]: 仅 can_sync 的服可点
    if can_sync:
        sync_str = my_lib.cmd("sync") + " " + name
        buttons.append(RText("[同步]", color=RColor.aqua).c(action, sync_str).h("同步主服存档到 {}".format(display)))
    else:
        buttons.append(RText("[同步]", color=RColor.gray).h("独立服务器，不支持同步"))
    buttons.append(" ")

    # [停止]/[开启]: 按当前在线状态切换
    if online:
        stop_str = my_lib.cmd("stop") + " " + name
        buttons.append(RText("[停止]", color=RColor.red).c(action, stop_str).h("关闭 {}".format(display)))
    else:
        start_str = my_lib.cmd("start") + " " + name
        buttons.append(RText("[开启]", color=RColor.green).c(action, start_str).h("启动 {}".format(display)))
    buttons.append(" ")

    # [重启]
    restart_str = my_lib.cmd("restart") + " " + name
    buttons.append(RText("[重启]", color=RColor.gold).c(action, restart_str).h("重启 {}".format(display)))

    source.reply(RTextList(*buttons))

    # 连接按钮: 走 Velocity 的 /server <英文名> (斜杠命令, run_command 全版本可点)
    if online:
        source.reply(
            RText("[连接到此服务器]", color=RColor.green)
            .c(RAction.run_command, "/server {}".format(name))
            .h("点击连接到 {} (/server {})".format(name, name))
        )
    else:
        source.reply(
            RText("[连接到此服务器]", color=RColor.dark_gray)
            .h("子服离线，暂时无法连接")
        )
