"""
sync.py — !!mscm sync <名字> [confirm]

把主服存档 (整个 world) 镜像同步到目标子服。

安全策略 (与用户确认):
- can_sync=false 的独立服拒绝同步;
- 目标子服在线则拒绝 (须先 stop);
- 同步前对主服 save-off + save-all flush, 完成后 save-on (放 finally, 保证恢复);
- 镜像式: 先清空目标世界再拷, 使子服与主服一致 (会删目标多余旧文件);
- session.lock 始终强制忽略, 叠加配置的 sync_ignore_files (正则);
- sync_whitelist (glob) 命中路径采用**子服自己的版本**: 镜像前先从旧目标里
  备份捞回、并从源拷贝中跳过, 实现「子服自有配置不被覆盖」;
- 破坏性操作, 需二次确认 ([确认]/[取消] 按钮或命令式 ... confirm / ... cancel)。

仅同步文件, 整个流程在 @new_thread 中执行, 避免阻塞 MCDR 主线程。
"""
import fnmatch
import os
import re
import shutil
import time

import mcdreforged as mcdr

from .. import my_lib
from ..slp import ServerListPing

TAG = my_lib.TAG

# save-all flush 后等待落盘的秒数
SAVE_FLUSH_WAIT = 3.0


def _server_port(cfg: dict) -> int:
    try:
        return int(cfg.get("port", 25565))
    except (TypeError, ValueError):
        return 25565


# ============================================================
# 忽略匹配
# ============================================================

def _build_ignore_matcher(patterns):
    """根据 sync_ignore_files 构造匹配函数。

    - 结尾带 '/' 的条目 -> 目录忽略 (该目录及其下全部);
    - 其余条目 -> 正则, 对「相对 sync_source 的相对路径」(以 / 分隔) 做 re.search;
    - session.lock 始终强制忽略。
    返回: match(rel_path: str) -> bool
    """
    dir_prefixes = []
    regexes = []
    for raw in (patterns or []):
        if not isinstance(raw, str) or not raw.strip():
            continue
        pattern = raw.strip()
        # 仅用「斜杠归一化」后的串判断是否为目录条目, 不要拿它去编译正则
        # (否则会把正则里的反斜杠转义如 \. 破坏成 /.)
        normalized = pattern.replace("\\", "/")
        if normalized.endswith("/"):
            dir_prefixes.append(normalized.rstrip("/"))
        else:
            try:
                regexes.append(re.compile(pattern))
            except re.error:
                regexes.append(re.compile(re.escape(pattern)))

    def match(rel_path: str) -> bool:
        rel = rel_path.replace("\\", "/")
        base = rel.rsplit("/", 1)[-1]
        if base == "session.lock":
            return True
        for prefix in dir_prefixes:
            if rel == prefix or rel.startswith(prefix + "/"):
                return True
        for rx in regexes:
            if rx.search(rel):
                return True
        return False

    return match


# ============================================================
# 白名单匹配 (子服自有文件优先)
# ============================================================

# 永远不参与同步的文件名 (运行中的锁文件, 拷过去会坏档)
ALWAYS_IGNORED_NAMES = {"session.lock"}


def _normalize_rel(path: str) -> str:
    """相对路径归一化: 反斜杠转斜杠, 去掉开头的 ./ 与 /"""
    rel = str(path or "").replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel.lstrip("/")


def _build_whitelist_matcher(patterns):
    """根据 sync_whitelist 构造匹配函数 (glob 语法)。

    - 结尾带 '/' 的条目 -> 目录条目, 命中该目录及其下全部文件;
    - 其余条目 -> glob (fnmatch), 对「相对 sync_source 的相对路径」做匹配;
      若条目里不含 '/', 则额外按文件名匹配 —— 这样写 'carpet.conf' 也能命中
      'config/carpet.conf', 更符合直觉;
    - 大小写不敏感 (与 Windows 文件系统语义一致);
    - session.lock 永不命中 (白名单也不能把它复活)。

    返回: match(rel_path: str) -> bool; 没有任何有效条目时返回 **None**
    (调用方据此跳过多余的遍历开销)。
    """
    # 容错: 用户可能只写了一个字符串而非列表。若直接迭代字符串会拆成单字符,
    # 白名单将静默失效 (还会白白多遍历一遍备份目录), 故先归一化为列表。
    if isinstance(patterns, str):
        patterns = [patterns]

    dir_prefixes = []      # 归一化后的小写目录前缀
    globs = []             # (小写 pattern, 是否同时匹配文件名)

    for raw in (patterns or []):
        if not isinstance(raw, str) or not raw.strip():
            continue
        pattern = _normalize_rel(raw.strip())
        if not pattern:
            continue
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/").lower()
            if prefix:
                dir_prefixes.append(prefix)
            continue
        globs.append((pattern.lower(), "/" not in pattern))

    if not dir_prefixes and not globs:
        return None

    def match(rel_path: str) -> bool:
        rel = _normalize_rel(rel_path).lower()
        base = rel.rsplit("/", 1)[-1]
        if base in ALWAYS_IGNORED_NAMES:
            return False
        for prefix in dir_prefixes:
            if rel == prefix or rel.startswith(prefix + "/"):
                return True
        for pattern, by_basename in globs:
            if fnmatch.fnmatchcase(rel, pattern):
                return True
            if by_basename and fnmatch.fnmatchcase(base, pattern):
                return True
        return False

    return match


def _restore_whitelisted(bak_root, target_root, whitelist):
    """把旧目标 (已改名为 .mscm_bak) 中命中白名单的文件拷回新目标。

    镜像同步会先把目标整体挪走、再据源重建, 所以「保留子服自己的版本」
    必须在这一步从备份里捞回来 —— 光靠「跳过不拷」是拿不回旧文件的。

    恢复失败**必须抛出**: 白名单路径既不会被源覆盖, 也不在源拷贝范围内,
    它在备份里的那份就是唯一副本。若在这里"记日志继续", 后续会照常删掉
    .mscm_bak, 导致子服这份配置永久丢失, 而且对外还报同步成功。
    抛异常会让 _mirror_copy 走回滚 (把备份改回原样), 保证不丢数据。

    :return: 成功拷回的文件数
    :raises RuntimeError: 任一白名单文件恢复失败 (已附带具体路径与原错误)
    """
    restored = 0
    for dirpath, _dirnames, filenames in os.walk(bak_root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, bak_root).replace("\\", "/")
            if not whitelist(rel):
                continue
            target_path = os.path.join(target_root, os.path.relpath(full, bak_root))
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(full, target_path)
                restored += 1
            except OSError as e:
                my_lib._log("[MSC] 白名单文件恢复失败 {}: {}".format(rel, e))
                raise RuntimeError(
                    "白名单文件恢复失败 {} ({})，已中止同步并回滚".format(rel, e)
                ) from e
    return restored


def _mirror_copy(source_root, target_root, matcher, whitelist=None):
    """镜像复制 (可回滚): 把现有目标改名为备份, 拷贝完成后再删备份;
    中途出错则删掉半成品、把备份改回原样, 保证子服存档不被破坏。

    :param matcher: 忽略匹配 (sync_ignore_files), 命中则不从源拷贝
    :param whitelist: 白名单匹配 (sync_whitelist)。命中路径**采用目标自己的版本**:
        1) 先把旧目标里这些文件从备份捞回新目标;
        2) 再从源拷贝时跳过它们 (源的版本不覆盖)。
        为 None 表示无白名单, 完全不产生额外开销。

    :return: (从源复制的文件数, 白名单恢复数)

    :raises RuntimeError: 白名单文件恢复失败 (此时已回滚, 目标保持原样)

    注意: 拷贝期间「旧存档(.mscm_bak) + 新存档」会同时存在, 峰值磁盘占用约为
    存档大小的 2 倍; 完成或回滚后备份即被清理。
    """
    source_root = os.path.normpath(source_root)
    target_root = os.path.normpath(target_root)
    bak = target_root + ".mscm_bak"

    # 清理上一次失败可能残留的备份
    if os.path.exists(bak):
        shutil.rmtree(bak, ignore_errors=True)

    had_target = os.path.isdir(target_root)
    moved_to_bak = False
    restored = 0
    try:
        if had_target:
            # 瞬时改名 (同盘, 不复制)
            os.replace(target_root, bak)
            moved_to_bak = True

        os.makedirs(target_root, exist_ok=True)

        # 1) 白名单: 先从旧目标把「子服自己的版本」捞回来
        #    (镜像同步会清空目标, 不在这里拷贝就等于丢失子服配置)
        if whitelist is not None and moved_to_bak:
            restored = _restore_whitelisted(bak, target_root, whitelist)

        # 2) 再从源拷贝, 但跳过白名单路径 (源版本不覆盖子服版本)
        copied = 0
        for dirpath, _dirnames, filenames in os.walk(source_root):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, source_root).replace("\\", "/")
                if matcher(rel):
                    continue
                if whitelist is not None and whitelist(rel):
                    continue
                target_path = os.path.join(target_root, os.path.relpath(full, source_root))
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(full, target_path)
                copied += 1
    except BaseException:
        # 回滚: 删掉半成品目标, 把备份改回原样
        shutil.rmtree(target_root, ignore_errors=True)
        if moved_to_bak:
            try:
                os.replace(bak, target_root)
            except OSError as re_err:
                my_lib._log(
                    "[MSC] 同步回滚失败, 原存档备份保留在: {} ({})".format(bak, re_err)
                )
        raise

    # 成功: 删除备份
    if moved_to_bak:
        shutil.rmtree(bak, ignore_errors=True)
    return copied, restored


# ============================================================
# 校验
# ============================================================

def _validate(source, name):
    """校验子服配置是否可同步; 通过返回 cfg, 否则回复并返回 None。"""
    cfg = my_lib.get_server(name)
    if cfg is None:
        source.reply(TAG + "§c未找到子服务器 §e{}§c，使用 §b{} §c查看列表".format(name, my_lib.cmd("show")))
        return None
    if not cfg.get("can_sync", False):
        source.reply(TAG + "§c子服 §e{}§c 为独立服务器 (can_sync=false)，不支持同步".format(name))
        return None
    if not (cfg.get("sync_source") or "") or not (cfg.get("sync_target") or ""):
        source.reply(TAG + "§c子服 §e{}§c 未配置 §esync_source§c / §esync_target".format(name))
        return None
    return cfg


# ============================================================
# 命令入口
# ============================================================

def sync_prompt(source: mcdr.CommandSource, context: dict):
    """!!mscm sync <名字> —— 校验并弹出二次确认。"""
    name = context["server_name"]
    cfg = _validate(source, name)
    if cfg is None:
        return
    display = cfg.get("cn_name") or name
    confirm_cmd = my_lib.cmd("sync") + " " + name + " confirm"
    cancel_cmd = my_lib.cmd("sync") + " " + name + " cancel"
    my_lib.send_confirm(
        source,
        "§e即将把主服存档全量同步到 §6{}".format(display),
        confirm_cmd, cancel_cmd,
        warn="§c此操作会用主服 world 镜像覆盖子服存档（删除目标多余旧文件），不可撤销！",
    )


def sync_confirm(source: mcdr.CommandSource, context: dict):
    """!!mscm sync <名字> confirm —— 校验后执行同步。"""
    name = context["server_name"]
    cfg = _validate(source, name)
    if cfg is None:
        return
    _run_sync(source, name, cfg)


# ============================================================
# 实际执行 (新线程)
# ============================================================

def sync_core(source: mcdr.CommandSource, name: str, cfg: dict, check_online: bool = True) -> bool:
    """阻塞执行一次全量同步, 返回是否成功。

    :param check_online: 是否在同步前检查目标子服是否在线 (restart 场景已先 stop, 可传 False)。

    并发约定: **调用方必须已持有全局同步锁 (my_lib.try_acquire_sync)**, 本函数不自行加锁。
    因为同步会对主服 save-off/save-on (全局状态), 必须保证全服同一时刻只有一个同步在跑。
    (手动 sync 见 _run_sync; restart sync 见 control._run_restart, 二者都在入口处先抢锁。)
    """
    server = my_lib.plugin_server
    display = cfg.get("cn_name") or name
    source_root = cfg.get("sync_source")
    target_root = cfg.get("sync_target")
    host = cfg.get("host", "127.0.0.1")
    port = _server_port(cfg)

    if not os.path.isdir(source_root):
        source.reply(TAG + "§c同步源目录不存在：§e{}".format(source_root))
        return False

    # 安全: 目标子服在线则拒绝
    if check_online and ServerListPing.is_online(host, port, timeout=my_lib.get_probe_timeout()):
        source.reply(TAG + "§c目标子服 §e{}§c 正在运行，请先关闭它再同步".format(display))
        return False

    matcher = _build_ignore_matcher(cfg.get("sync_ignore_files"))
    whitelist = _build_whitelist_matcher(cfg.get("sync_whitelist"))

    source.reply(TAG + "§2开始全量同步 §6{}§2……请稍候".format(display))
    main_running = server is not None and server.is_server_running()
    start_ts = time.time()

    # 同步前关闭主服自动保存并强制落盘
    if main_running:
        server.execute("save-off")
        server.execute("save-all flush")
        time.sleep(SAVE_FLUSH_WAIT)

    copied = -1
    restored = 0
    try:
        copied, restored = _mirror_copy(source_root, target_root, matcher, whitelist)
    except Exception as e:  # noqa: BLE001 - 同步失败需把错误反馈给执行者
        source.reply(TAG + "§c同步失败：{}".format(e))
        my_lib._log("[MSC] 同步 {} 失败: {}".format(name, e))
    finally:
        # 无论成败都恢复主服自动保存
        if main_running:
            server.execute("save-on")

    if copied >= 0:
        msg = TAG + "§a同步完成！§r共复制 §e{}§r 个文件".format(copied)
        if restored > 0:
            msg += "，保留子服自有 §e{}§r 个 (白名单)".format(restored)
        msg += "，用时 §e{:.1f}s".format(time.time() - start_ts)
        source.reply(msg)
        my_lib._log(
            "[MSC] 同步 {} 完成: 复制 {} 个, 白名单保留 {} 个".format(name, copied, restored)
        )
        my_lib.dispatch_event("server_synced", (name,))
        return True
    return False


@mcdr.new_thread("MSC-sync")
def _run_sync(source: mcdr.CommandSource, name: str, cfg: dict):
    """手动同步入口: 先抢该子服的操作锁 (排斥其 start/stop/restart), 再抢全局同步锁
    (排斥其它同步), 都拿到才真正执行。任一被占用则提示并退出, 不做任何破坏性操作。
    """
    display = cfg.get("cn_name") or name
    busy = my_lib.try_acquire_op(name, "同步")
    if busy:
        source.reply(TAG + "§6{}§e 正在§6{}§e中，请稍候".format(display, busy))
        return
    try:
        if not my_lib.try_acquire_sync():
            source.reply(TAG + "§e已有同步任务正在进行，请等待其完成后再试")
            return
        try:
            sync_core(source, name, cfg)
        finally:
            my_lib.release_sync()
    finally:
        my_lib.release_op(name)
