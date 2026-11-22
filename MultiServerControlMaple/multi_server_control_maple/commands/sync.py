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
import tempfile
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


# ============================================================
# 额外同步项 (sync_extra): 把 world 之外的文件/目录一并同步
# ============================================================

def _norm_path(path: str) -> str:
    """路径归一化 (绝对化 + 规范化 + 统一大小写), 仅用于比较包含关系"""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _is_inside(child: str, parent: str) -> bool:
    """child 是否等于 parent 或位于 parent 内部 (大小写不敏感, Windows 语义)"""
    if not parent:
        return False
    c, p = _norm_path(child), _norm_path(parent)
    return c == p or c.startswith(p + os.sep)


def _overlaps(a: str, b: str) -> bool:
    """两个路径是否存在任何重叠 (相等 / 一方在另一方内部)。

    必须用双向判断: 只判断「a 在 b 内」会漏掉「a 是 b 的祖先」的情况 ——
    例如额外项源配成 ./server (它包含 ./server/world), 单向判断会放行,
    随后会把整个 world 再拷一遍, 绕过 sync_ignore_files / sync_whitelist。
    """
    return _is_inside(a, b) or _is_inside(b, a)


def _parse_extra_items(cfg: dict):
    """解析并校验 sync_extra 配置。

    :return: ([(源绝对路径, 目标绝对路径), ...], [错误信息, ...])

    设计约定: 任何一项配置错误都**拒绝整次同步** (而不是跳过该项),
    否则用户会以为同步完整成功。校验项:
      - source / target 均必填
      - source 必须存在
      - **source 不得位于 world 同步源内** (那部分已由 world 同步覆盖, 重复配置会互相打架)
      - target 不得位于 world 同步目标内 (同理)
      - source 与 target 不得相同, target 不得位于 source 内部 (会造成自我递归拷贝)
    """
    raw = cfg.get("sync_extra")
    if not raw:
        return [], []
    if not isinstance(raw, list):
        return [], ["sync_extra 必须是列表，每项形如 {\"source\": \"...\", \"target\": \"...\"}"]

    sync_source = cfg.get("sync_source") or ""
    sync_target = cfg.get("sync_target") or ""

    items = []
    errors = []
    for index, entry in enumerate(raw, 1):
        tag = "第 {} 项".format(index)
        if not isinstance(entry, dict):
            errors.append("{} 格式错误 (应为 {{\"source\": ..., \"target\": ...}})".format(tag))
            continue
        src = str(entry.get("source") or "").strip()
        tgt = str(entry.get("target") or "").strip()
        if not src or not tgt:
            errors.append("{} 缺少 source 或 target".format(tag))
            continue

        src_abs = os.path.abspath(src)
        tgt_abs = os.path.abspath(tgt)

        if not os.path.exists(src_abs):
            errors.append("{} 源不存在: {}".format(tag, src_abs))
            continue
        # 与 world 同步的源/目标**双向**互不重叠:
        # 单向判断会漏掉「额外项源是 world 父目录」的情况 (如 ./server 包含 ./server/world),
        # 那样会把整个 world 重复拷一遍, 绕过 ignore / 白名单, 覆盖子服自有配置。
        if _overlaps(src_abs, sync_source):
            errors.append(
                "{} 源与 world 同步源重叠 (不能是它的父目录或内部路径): {}".format(tag, src_abs)
            )
            continue
        if _overlaps(tgt_abs, sync_target):
            errors.append(
                "{} 目标与 world 同步目标重叠 (不能是它的父目录或内部路径): {}".format(tag, tgt_abs)
            )
            continue
        # 额外项不得写进主服 world, 也不应从子服 world 读取
        if sync_source and _is_inside(tgt_abs, sync_source):
            errors.append("{} 目标不能位于主服 world 内: {}".format(tag, tgt_abs))
            continue
        if sync_target and _is_inside(src_abs, sync_target):
            errors.append("{} 源不能位于子服 world 内: {}".format(tag, src_abs))
            continue
        if _norm_path(src_abs) == _norm_path(tgt_abs):
            errors.append("{} 源与目标相同: {}".format(tag, src_abs))
            continue
        if _is_inside(tgt_abs, src_abs):
            errors.append("{} 目标不能位于源内部 (会自我递归拷贝): {}".format(tag, tgt_abs))
            continue

        items.append((src_abs, tgt_abs))

    return items, errors


def _rollback_extra(backups: dict, created_files: list, created_dirs: list):
    """回滚单个额外项: 恢复被覆盖的文件, 删除新建的文件与新建的空目录。"""
    for dest, bak_path in backups.items():
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(bak_path, dest)
        except OSError as e:
            my_lib._log("[MSC] 额外项回滚失败(恢复) {}: {}".format(dest, e))
    for dest in created_files:
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError as e:
            my_lib._log("[MSC] 额外项回滚失败(删除) {}: {}".format(dest, e))
    # 由深到浅删空目录 (rmdir 只会删空目录, 失败即说明里面有别的东西, 忽略)
    for directory in reversed(created_dirs):
        try:
            os.rmdir(directory)
        except OSError:
            pass


def _sync_extra_item(src: str, tgt: str):
    """把一个额外项从源同步到目标 (**合并语义**, 单项失败自动回滚)。

    - 源是**目录**: 递归拷贝其下所有文件, 覆盖目标同名文件;
      **目标独有的文件保留不动** (便于插件配置目录这类场景)
    - 源是**文件**: 直接覆盖目标同名文件

    与 world 同步的区别: 这里不做「整目录改名备份」, 而是逐文件备份,
    因此子服原有的其他文件不会丢; 失败时把已覆盖的文件恢复原内容、
    把新建的文件删掉。

    :return: (成功拷贝的文件数, 错误信息或 None)
    """
    created_files = []
    created_dirs = []
    backups = {}
    # 备份放系统临时目录, 避免污染目标目录; copy2 支持跨盘。
    # 必须在 try 内部创建: 创建失败 (TEMP 不可用/磁盘满/权限) 也要走回滚与错误上报,
    # 不能把异常抛给调用方中断整轮额外项同步。
    backup_dir = None
    try:
        backup_dir = tempfile.mkdtemp(prefix="mscm_extra_bak_")
        if os.path.isdir(src):
            pairs = []
            for dirpath, _dirnames, filenames in os.walk(src):
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, src)
                    pairs.append((full, os.path.join(tgt, rel)))
        else:
            pairs = [(src, tgt)]

        if not pairs:
            return 0, None  # 空目录, 无事可做

        for full, dest in pairs:
            parent = os.path.dirname(dest)
            if parent and not os.path.isdir(parent):
                # 记录本次新建的各级目录, 供回滚时按由深到浅清理
                missing = []
                cur = parent
                while cur and not os.path.isdir(cur):
                    missing.append(cur)
                    nxt = os.path.dirname(cur)
                    if nxt == cur:
                        break
                    cur = nxt
                os.makedirs(parent, exist_ok=True)
                created_dirs.extend(reversed(missing))  # 浅 -> 深

            if os.path.exists(dest):
                bak_path = os.path.join(backup_dir, str(len(backups)))
                shutil.copy2(dest, bak_path)
                backups[dest] = bak_path
            else:
                created_files.append(dest)

            shutil.copy2(full, dest)

        return len(pairs), None
    except BaseException as e:  # noqa: BLE001 - 需先回滚再上报
        _rollback_extra(backups, created_files, created_dirs)
        return 0, e
    finally:
        if backup_dir:
            shutil.rmtree(backup_dir, ignore_errors=True)


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

    # 额外同步项 (world 之外的文件/目录): 配置错误直接拒绝整次同步,
    # 避免用户误以为同步完整成功却漏了关键配置。
    extra_items, extra_errors = _parse_extra_items(cfg)
    if extra_errors:
        for err in extra_errors:
            source.reply(TAG + "§c[额外同步] " + err)
            my_lib._log("[MSC] 同步 {} 的 sync_extra 配置错误: {}".format(name, err))
        source.reply(TAG + "§c同步已中止: 请修正 §esync_extra §c配置后重试")
        return False

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
        # ---- 额外同步项 (world 同步成功后才做; 单项失败只回滚该项) ----
        extra_copied = 0
        extra_failed = []
        for index, (src_path, tgt_path) in enumerate(extra_items, 1):
            # 防御: 即使 _sync_extra_item 自身抛出预期外异常, 也只影响该项,
            # 不能让整轮额外项同步中断 (否则收不到汇总, 也漏了后面的项)。
            try:
                files, err = _sync_extra_item(src_path, tgt_path)
            except Exception as e:  # noqa: BLE001 - 单项异常不应中断整轮
                files, err = 0, e
            if err is None:
                extra_copied += files
                my_lib._log(
                    "[MSC] 额外同步 {}/{} 完成: {} -> {} ({} 个文件)".format(
                        index, len(extra_items), src_path, tgt_path, files
                    )
                )
            else:
                extra_failed.append(src_path)
                source.reply(
                    TAG + "§c[额外同步] 失败: §e{}§c ({})".format(src_path, err)
                )
                my_lib._log(
                    "[MSC] 额外同步 {}/{} 失败: {} -> {}: {}".format(
                        index, len(extra_items), src_path, tgt_path, err
                    )
                )

        msg = TAG + "§a同步完成！§r共复制 §e{}§r 个文件".format(copied)
        if restored > 0:
            msg += "，保留子服自有 §e{}§r 个 (白名单)".format(restored)
        if extra_items:
            msg += "，额外项 §e{}§r 个文件".format(extra_copied)
            if extra_failed:
                msg += " §c({} 项失败)".format(len(extra_failed))
        msg += "，用时 §e{:.1f}s".format(time.time() - start_ts)
        source.reply(msg)
        my_lib._log(
            "[MSC] 同步 {} 完成: 复制 {} 个, 白名单保留 {} 个, 额外项 {} 个文件, 失败 {} 项".format(
                name, copied, restored, extra_copied, len(extra_failed)
            )
        )

        if extra_failed:
            # 额外项不完整时不派发同步完成事件, 避免下游误判子服已完全一致
            source.reply(
                TAG + "§e注意: 有额外同步项失败, 子服可能缺少必要配置; "
                "§7已跳过 §fserver_synced§7 事件派发"
            )
            return True

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
