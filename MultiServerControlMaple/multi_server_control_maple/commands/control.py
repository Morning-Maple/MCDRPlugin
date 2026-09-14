"""
control.py — 子服进程控制: start / stop / restart

- start   : !!mscm start <名字>                    （无需确认）
- stop    : !!mscm stop <名字> [confirm]            （会踢下线, 需二次确认; 依赖 rcon）
- restart : !!mscm restart <名字> [confirm]         （stop -> 等停 -> start, 需二次确认）
            !!mscm restart <名字> sync [confirm]     （stop -> 同步主服存档 -> start）

关键约定 (与用户确认):
- **仅 Windows**: start 用 subprocess.Popen + CREATE_NEW_CONSOLE 开独立新控制台窗口, cwd=path
  (不用 os.chdir 改主进程工作目录, 避免多线程竞态)。
- 在线判定统一用 SLP (ServerListPing.is_online)。
- stop 走 rcon (host + rcon_port + rcon_password), 需 rcon_enable。
- restart 里 stop 后轮询等端口/SLP 离线 (带超时), 而非死等固定秒数。
- 同名子服的 start/stop/restart 互斥, 防重复提交。
"""
import os
import subprocess
import sys
import threading
import time

import mcdreforged as mcdr
from mcdreforged.api.rcon import RconConnection

from .. import my_lib
from ..slp import ServerListPing
from . import sync as sync_cmd

TAG = my_lib.TAG

# Windows 下开新控制台窗口的标志; 非 Windows 为 0 (start 本就仅支持 Windows)
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

# restart 中 stop 后, 等待子服真正离线的最长秒数与轮询间隔
STOP_WAIT_TIMEOUT = 60
STOP_POLL_INTERVAL = 2.0


# ============================================================
# 并发互斥
#   按子服的操作锁集中在 my_lib (try_acquire_op / release_op), 供 control 与 sync 共用;
#   在整个「启动并监听」窗口内持有, 期间其它 start/stop/restart/sync 会被挡下。
# ============================================================

# 插件卸载信号: 置位后, 后台监听线程 (启动监听 / 等待离线轮询) 会尽快退出, 不再空转到超时。
_shutdown = threading.Event()


def on_unload():
    """插件卸载: 通知后台线程尽快退出, 并清空占用标记。"""
    _shutdown.set()
    my_lib.clear_ops()


# ============================================================
# 小工具
# ============================================================

def _server_port(cfg: dict) -> int:
    try:
        return int(cfg.get("port", 25565))
    except (TypeError, ValueError):
        return 25565


def _rcon_port(cfg: dict) -> int:
    try:
        return int(cfg.get("rcon_port", 25575))
    except (TypeError, ValueError):
        return 25575


def _is_online(cfg: dict) -> bool:
    return ServerListPing.is_online(
        cfg.get("host", "127.0.0.1"), _server_port(cfg), timeout=my_lib.get_probe_timeout()
    )


def _probe_status(cfg: dict):
    """完整探测子服状态 (含在线人数/玩家名单); 离线返回 None。"""
    return ServerListPing.ping(
        cfg.get("host", "127.0.0.1"), _server_port(cfg),
        timeout=my_lib.get_probe_timeout(), with_latency=False,
    )


def _players_warn(status) -> str:
    """根据探测结果生成「是否还有人」的提示文案。"""
    if status is None:
        return "§7无法确认目标服务器在线状态。"
    if status.online <= 0:
        return "§7当前无玩家在线。"
    names = "：" + "、".join(status.players) if status.players else ""
    return "§c目标服务器还有 §e{}§c 名玩家在线{}，确定要操作吗？".format(status.online, names)


def _display(name: str, cfg: dict) -> str:
    return cfg.get("cn_name") or name


def _get_cfg(source: mcdr.CommandSource, name: str):
    cfg = my_lib.get_server(name)
    if cfg is None:
        source.reply(TAG + "§c未找到子服务器 §e{}§c，使用 §b{} §c查看列表".format(name, my_lib.cmd("show")))
        return None
    return cfg


def _confirm_cmds(base_cmd: str):
    """给定命令前半段 (如 '!!mscm stop mirror'), 返回 (确认命令, 取消命令)。"""
    return base_cmd + " confirm", base_cmd + " cancel"


# ============================================================
# 启动进程
# ============================================================

def _launch(source, name: str, cfg: dict) -> bool:
    """按 start_command 在 path 下开独立新控制台窗口启动子服。返回是否成功发起。"""
    path = cfg.get("path") or ""
    start_command = cfg.get("start_command")

    if sys.platform != "win32":
        source.reply(TAG + "§c子服启动仅支持 Windows")
        return False
    if not path or not start_command:
        source.reply(TAG + "§c子服 §e{}§c 未配置 §epath§c / §estart_command".format(name))
        return False
    if not os.path.isdir(path):
        source.reply(TAG + "§cpath 目录不存在：§e{}".format(path))
        return False

    # list -> 多条命令; str -> 单条 (path 下的脚本文件)
    commands = start_command if isinstance(start_command, list) else [start_command]
    commands = [c for c in commands if isinstance(c, str) and c.strip()]
    if not commands:
        source.reply(TAG + "§cstart_command 为空")
        return False
    joined = " && ".join(commands)

    try:
        # cmd /c: 命令(子服进程)退出后自动关闭该控制台窗口
        subprocess.Popen(["cmd", "/c", joined], cwd=path, creationflags=CREATE_NEW_CONSOLE)
        return True
    except Exception as e:  # noqa: BLE001
        source.reply(TAG + "§c启动 §e{}§c 失败：{}".format(name, e))
        my_lib._log("[MSC] 启动 {} 失败: {}".format(name, e))
        return False


# ============================================================
# 关闭进程 (rcon)
# ============================================================

def _do_stop(source, name: str, cfg: dict) -> bool:
    """通过 rcon 向子服发送 stop。返回是否成功发送。

    无论成功与否都在 finally 里 disconnect, 确保 rcon socket 及时释放。
    """
    host = cfg.get("host", "127.0.0.1")
    conn = RconConnection(host, _rcon_port(cfg), cfg.get("rcon_password", ""))
    connected = False
    try:
        connected = conn.connect()
        if not connected:
            source.reply(TAG + "§c无法连接 §e{}§c 的 rcon（检查 rcon_port / rcon_password / 是否已开启）".format(name))
            return False
        conn.send_command("stop", max_retry_time=3)
        return True
    except Exception as e:  # noqa: BLE001
        source.reply(TAG + "§c通过 rcon 关闭 §e{}§c 失败：{}".format(name, e))
        my_lib._log("[MSC] 关闭 {} 失败: {}".format(name, e))
        return False
    finally:
        if connected:
            try:
                conn.disconnect()
            except Exception:  # noqa: BLE001 - 关闭连接的异常无需上报
                pass


# ============================================================
# 启动并监听 (发出启动命令后轮询 SLP, 直到在线或超时)
# ============================================================

def _start_and_wait(source, name: str, cfg: dict) -> bool:
    """发出启动命令并在本线程内轮询监听启动情况。

    调用方需已持有该子服的操作锁 (my_lib.try_acquire_op), 使整个监听窗口内互斥。
    返回是否成功发出启动命令 (监听超时不算失败, 只是无法确认在线)。
    """
    if not _launch(source, name, cfg):
        return False
    display = _display(name, cfg)
    timeout = my_lib.get_startup_timeout()
    interval = max(1.0, my_lib.get_startup_poll_interval())
    source.reply(TAG + "§6{}§a 启动命令已执行，正在监听启动状态（最多 §e{:.0f}s§a）……".format(display, timeout))

    waited = 0.0
    while waited < timeout:
        # 用 Event.wait 兼作 sleep: 卸载时立即返回, 线程随即结束
        if _shutdown.wait(interval):
            return True
        waited += interval
        if _is_online(cfg):
            source.reply(TAG + "§6{}§a 已成功启动！可用 §b/server {} §a连接（需 Velocity）".format(display, name))
            return True
    source.reply(
        TAG + "§6{}§e 已发出启动命令，但 §c{:.0f}s§e 内未检测到在线，可能仍在启动或启动失败，请手动确认".format(display, timeout)
    )
    return True


# ============================================================
# start
# ============================================================

@mcdr.new_thread("MSC-start")
def start_cmd(source: mcdr.CommandSource, context: dict):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    display = _display(name, cfg)
    busy = my_lib.try_acquire_op(name, "启动")
    if busy:
        source.reply(TAG + "§6{}§e 正在§6{}§e中，请稍候".format(display, busy))
        return
    try:
        if _is_online(cfg):
            source.reply(TAG + "§6{}§f 已在运行，无须启动".format(display))
            return
        source.reply(TAG + "§a正在启动 §6{}§a……".format(display))
        if _start_and_wait(source, name, cfg) and not _shutdown.is_set():
            my_lib.dispatch_event("server_start", (name,))
    finally:
        my_lib.release_op(name)


# ============================================================
# stop
# ============================================================

def stop_prompt(source: mcdr.CommandSource, context: dict):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    display = _display(name, cfg)
    if not cfg.get("rcon_enable", False):
        source.reply(TAG + "§c子服 §e{}§c 未开启 rcon（rcon_enable=false），无法关闭".format(display))
        return
    status = _probe_status(cfg)
    if status is None:
        source.reply(TAG + "§6{}§f 已处于关闭状态，无须关闭".format(display))
        return
    confirm_cmd, cancel_cmd = _confirm_cmds(my_lib.cmd("stop") + " " + name)
    my_lib.send_confirm(
        source,
        "§e即将关闭子服 §6{}§e（服上玩家会被踢下线）".format(display),
        confirm_cmd, cancel_cmd,
        warn=_players_warn(status),
    )


def stop_confirm(source: mcdr.CommandSource, context: dict):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    if not cfg.get("rcon_enable", False):
        source.reply(TAG + "§c子服 §e{}§c 未开启 rcon，无法关闭".format(_display(name, cfg)))
        return
    _run_stop(source, name, cfg)


@mcdr.new_thread("MSC-stop")
def _run_stop(source: mcdr.CommandSource, name: str, cfg: dict):
    display = _display(name, cfg)
    busy = my_lib.try_acquire_op(name, "关闭")
    if busy:
        source.reply(TAG + "§6{}§e 正在§6{}§e中，请稍候".format(display, busy))
        return
    try:
        if not _is_online(cfg):
            source.reply(TAG + "§6{}§f 已处于关闭状态，无须关闭".format(display))
            return
        source.reply(TAG + "§a正在关闭 §6{}§a……".format(display))
        if _do_stop(source, name, cfg):
            # 轮询等待真正离线, 避免紧接着 start 撞上未退出的旧进程
            waited = 0.0
            while _is_online(cfg) and waited < STOP_WAIT_TIMEOUT:
                if _shutdown.wait(STOP_POLL_INTERVAL):
                    return
                waited += STOP_POLL_INTERVAL
            if _is_online(cfg):
                source.reply(
                    TAG + "§6{}§e 已发送关闭命令，但 §c{:.0f}s§e 内未检测到离线，请手动确认".format(display, STOP_WAIT_TIMEOUT)
                )
                return
            source.reply(TAG + "§6{}§a 已关闭".format(display))
            my_lib.dispatch_event("server_stop", (name,))
    finally:
        my_lib.release_op(name)


# ============================================================
# restart
# ============================================================

def restart_prompt(source: mcdr.CommandSource, context: dict):
    _restart_prompt(source, context, do_sync=False)


def restart_sync_prompt(source: mcdr.CommandSource, context: dict):
    _restart_prompt(source, context, do_sync=True)


def _restart_prompt(source, context, do_sync: bool):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    display = _display(name, cfg)
    if do_sync and not cfg.get("can_sync", False):
        source.reply(TAG + "§c子服 §e{}§c 为独立服务器（can_sync=false），不能同步；如需重启请用不带 sync 的命令".format(display))
        return
    action = "同步并重启" if do_sync else "重启"
    base_cmd = my_lib.cmd("restart") + " " + name + (" sync" if do_sync else "")
    confirm_cmd, cancel_cmd = _confirm_cmds(base_cmd)
    status = _probe_status(cfg)
    flow = "同步主服存档后再启动。" if do_sync else "待完全停止后再启动。"
    warn = _players_warn(status) + "\n§7在线时将先经 rcon 关闭（玩家会被踢下线），" + flow
    my_lib.send_confirm(source, "§e即将{} §6{}".format(action, display), confirm_cmd, cancel_cmd, warn=warn)


def restart_confirm(source: mcdr.CommandSource, context: dict):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    _run_restart(source, name, cfg, do_sync=False)


def restart_sync_confirm(source: mcdr.CommandSource, context: dict):
    name = context["server_name"]
    cfg = _get_cfg(source, name)
    if cfg is None:
        return
    if not cfg.get("can_sync", False):
        source.reply(TAG + "§c子服 §e{}§c 为独立服务器（can_sync=false），不能同步".format(_display(name, cfg)))
        return
    _run_restart(source, name, cfg, do_sync=True)


@mcdr.new_thread("MSC-restart")
def _run_restart(source: mcdr.CommandSource, name: str, cfg: dict, do_sync: bool):
    display = _display(name, cfg)
    op = "同步并重启" if do_sync else "重启"
    busy = my_lib.try_acquire_op(name, op)
    if busy:
        source.reply(TAG + "§6{}§e 正在§6{}§e中，请稍候".format(display, busy))
        return
    sync_locked = False
    try:
        # do_sync: 先抢全局同步锁再动手, 避免「已停服却因别处正在同步而无法同步」的中途搁浅。
        if do_sync:
            if not my_lib.try_acquire_sync():
                source.reply(TAG + "§e已有同步任务正在进行，{}已中止，请稍后再试".format(op))
                return
            sync_locked = True

        source.reply(TAG + "§6{}§f 开始执行§a{}§f……".format(display, op))

        # 1) 在线则先关闭并等待其离线
        if _is_online(cfg):
            if not cfg.get("rcon_enable", False):
                source.reply(TAG + "§c子服在线但未开启 rcon，无法关闭以重启".format())
                return
            source.reply(TAG + "§a正在关闭 §6{}§a……".format(display))
            if not _do_stop(source, name, cfg):
                return
            waited = 0.0
            while _is_online(cfg) and waited < STOP_WAIT_TIMEOUT:
                if _shutdown.wait(STOP_POLL_INTERVAL):
                    return  # 插件卸载, 中止重启
                waited += STOP_POLL_INTERVAL
            if _is_online(cfg):
                source.reply(TAG + "§c等待 §6{}§c 关闭超时（{}s），重启已中止".format(display, STOP_WAIT_TIMEOUT))
                return
            source.reply(TAG + "§6{}§a 已关闭".format(display))

        # 2) 可选: 同步主服存档 (此时子服已离线, 无须再检查在线; 已持有全局同步锁)
        if do_sync:
            if not sync_cmd.sync_core(source, name, cfg, check_online=False):
                source.reply(TAG + "§c同步失败，重启已中止")
                return

        # 3) 启动并监听
        source.reply(TAG + "§a正在启动 §6{}§a……".format(display))
        if _start_and_wait(source, name, cfg) and not _shutdown.is_set():
            my_lib.dispatch_event("server_restart", (name,))
    finally:
        if sync_locked:
            my_lib.release_sync()
        my_lib.release_op(name)
