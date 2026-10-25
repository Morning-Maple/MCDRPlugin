"""
advancement.py — 成就抓取 / 库存存储 / 分发

模型
----
stock (库存)   : 从某个玩家抓取的一份成就快照, 持久化在插件数据目录的
                 ``stock.json``, 抓取后可脱离原玩家独立存在。
give (分发)    : 把库存里的成就授予在线玩家。

技术要点
--------
读 (抓取):
    原版没有任何命令能「列出某玩家已有的成就」, 唯一数据源是存档文件
    ``<world>/advancements/<uuid>.json``。**只读**在线玩家的存档是安全的
    (服务器仅在保存时写回, 不会锁文件)。

写 (分发):
    在线玩家的成就在服务器内存里, 直接改存档文件会在下次保存时被覆盖。
    因此统一用 ``advancement grant <玩家> only <成就id>`` 让服务端自己改,
    即时生效且服务端权威。

注意: 原版**没有**「把 A 的成就复制给 B」的单条命令 —— ``grant ... from <x>``
里的 from 指的是进度树节点, 不是玩家。所以必须逐条授予。
"""
import json
import os
import tempfile
import time

from . import my_lib

# 库存文件名 (落在插件数据目录)
STOCK_FILE = "stock.json"

# ------------------------------------------------------------
# 库存内存态:
#   {
#     "source": 来源玩家名,
#     "uuid":   来源玩家 UUID,
#     "created_at": 抓取时间戳,
#     "ids":    [成就 id, ...]  (已排序)
#   }
# 未抓取时为 None。
# ------------------------------------------------------------
stock: dict = None


# ============================================================
# 路径解析
# ============================================================

def _abs_path(path: str) -> str:
    """把配置里的相对路径转为绝对路径 (相对 MCDR 工作目录)"""
    path = str(path or "")
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(path)


def get_advancements_dir() -> str:
    """玩家成就存档目录的绝对路径"""
    return _abs_path(my_lib.config.get("advancements_dir", "./server/world/advancements"))


def get_usercache_path() -> str:
    """usercache.json 的绝对路径"""
    return _abs_path(my_lib.config.get("usercache_path", "./server/usercache.json"))


def advancement_file(player_uuid: str) -> str:
    """某 UUID 对应的成就存档文件路径"""
    return os.path.join(get_advancements_dir(), f"{player_uuid}.json")


def _stock_path() -> str:
    """库存文件的绝对路径"""
    return os.path.join(my_lib.plugin_server.get_data_folder(), STOCK_FILE)


# ============================================================
# 库存 持久化
# ============================================================

def load_stock():
    """从文件加载库存到内存; 文件缺失或损坏时置空"""
    global stock
    path = _stock_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        stock = None
        return

    if not isinstance(raw, dict):
        stock = None
        return

    raw_ids = raw.get("ids")
    if not isinstance(raw_ids, list):
        stock = None
        return
    # 先过滤非法元素再判空 —— 否则「非空但全是非法元素」会得到一个
    # 看似有效却包含 0 个成就的库存, 让 give 静默"成功"、用户无从察觉。
    ids = [i for i in raw_ids if isinstance(i, str) and i]
    if not ids:
        stock = None
        return

    stock = {
        "source": str(raw.get("source") or "未知"),
        "uuid": str(raw.get("uuid") or ""),
        "created_at": raw.get("created_at") or 0,
        "ids": sorted(ids),
    }


def _atomic_write_json(path: str, data) -> None:
    """原子写 JSON: 先写同目录临时文件并 fsync, 再 os.replace 覆盖。"""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_stock() -> bool:
    """把内存库存写入文件 (原子写); 成功返回 True"""
    if stock is None:
        return False
    try:
        _atomic_write_json(_stock_path(), stock)
        return True
    except Exception as e:
        my_lib._log(f"[AdvMaple] 保存库存失败: {e}")
        return False


def get_stock() -> dict:
    """当前库存 (未抓取时为 None)"""
    return stock


# ============================================================
# usercache.json (玩家名 -> UUID, 支持离线玩家)
# ============================================================

_usercache_cache = {"mtime": None, "path": None, "by_name": {}}


def _refresh_usercache():
    """按 mtime 判断是否需要重新解析 usercache.json"""
    path = get_usercache_path()
    if not path:
        return
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return
    if _usercache_cache["mtime"] == mtime and _usercache_cache["path"] == path:
        return  # 命中缓存

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        my_lib._log(f"[AdvMaple] 读取 usercache 失败 ({path}): {e}")
        return

    by_name = {}
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            uuid_ = entry.get("uuid")
            if isinstance(name, str) and name and isinstance(uuid_, str) and uuid_:
                by_name[name.lower()] = uuid_

    _usercache_cache["mtime"] = mtime
    _usercache_cache["path"] = path
    _usercache_cache["by_name"] = by_name


def resolve_uuid(player_name: str):
    """玩家名 -> UUID 字符串。

    解析顺序:
      1. **先查 usercache.json** —— 纯本地文件读取 (带 mtime 缓存), 零延迟,
         且同时覆盖在线与离线玩家 (玩家进服时服务端会写入该文件)。
      2. usercache 未命中时才查 minecraft_data_api 兜底。

    顺序很重要: 若先查 API, **离线玩家会一直等到 API 的 5 秒查询超时**才回退,
    让抓取离线玩家的成就时白等 5 秒并在控制台刷超时警告。

    注意: 该函数可能阻塞 (走 API 兜底时), 只能在 @new_thread 中调用。
    """
    if not player_name:
        return None

    _refresh_usercache()
    uuid_ = _usercache_cache["by_name"].get(player_name.lower())
    if uuid_:
        return uuid_

    try:
        return my_lib.get_player_uuid(player_name)
    except Exception:
        return None


# ============================================================
# 成就存档读取 / 抓取
# ============================================================

def is_excluded(adv_id: str) -> bool:
    """该成就 id 是否被 exclude_prefixes 排除 (默认排除配方类)"""
    for prefix in my_lib.get_exclude_prefixes():
        if prefix and adv_id.startswith(prefix):
            return True
    return False


def read_player_advancements(player_uuid: str, *, missing_as_empty: bool = False):
    """读取某玩家已完成的成就 id 列表 (已排序)。

    判定规则:
      - 只算 ``done is True`` 的条目 (部分完成 done=false 不算)
      - 按 ``exclude_prefixes`` 过滤 (默认排除 ``minecraft:recipes/``)

    :param missing_as_empty: 存档文件**不存在**时是否当作「没有任何成就」。
        分发目标应传 True —— 新玩家从未获得成就时服务端不会生成该文件,
        若不区分会把所有新玩家误判为「读取失败」而跳过。
        抓取库存时应保持 False —— 文件不存在意味着没东西可抓, 应报错。

    :return: 成就 id 列表 (可能为空); **无法读取时返回 None**。
        注意: 文件存在但内容损坏/不完整时**始终**返回 None, 即使
        missing_as_empty=True —— 否则会把「读失败」误当成「零成就」,
        进而给该玩家灌入整份库存。两种情况必须严格区分。
    """
    path = advancement_file(player_uuid)
    exists = os.path.isfile(path)

    if not exists:
        return [] if missing_as_empty else None

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        # 文件存在却读不出来 = 损坏/被占用/正在写入 → 必须报失败, 不能当空
        my_lib._log(f"[AdvMaple] 读取成就存档失败 {path}: {e}")
        return None
    if not isinstance(raw, dict):
        my_lib._log(f"[AdvMaple] 成就存档结构异常 {path}")
        return None

    ids = []
    for adv_id, entry in raw.items():
        if not isinstance(adv_id, str) or not isinstance(entry, dict):
            continue
        if entry.get("done") is not True:
            continue
        if is_excluded(adv_id):
            continue
        ids.append(adv_id)
    return sorted(ids)


def grab(player_name: str):
    """从玩家抓取成就作为库存 (覆盖旧库存)。

    :return: (成功标志, 提示信息或成就数)
    """
    global stock

    player_uuid = resolve_uuid(player_name)
    if not player_uuid:
        return False, (
            "无法解析该玩家的 UUID\n"
            "§7  请确认玩家名正确, 并检查 §fusercache_path §7配置"
        )

    ids = read_player_advancements(player_uuid)
    if ids is None:
        return False, (
            "读取该玩家的成就存档失败\n"
            f"§7  查找路径: §f{advancement_file(player_uuid)}\n"
            "§7  请确认 §fadvancements_dir §7指向服务端的 advancements 目录"
        )

    if not ids:
        return False, "该玩家没有任何已完成的成就 (排除配方类后), 未创建库存"

    stock = {
        "source": player_name,
        "uuid": player_uuid,
        "created_at": time.time(),
        "ids": ids,
    }
    if not save_stock():
        return False, "库存创建成功但保存到文件失败, 重启后会丢失, 请检查日志"

    return True, len(ids)


# ============================================================
# 分发
# ============================================================

def compute_diff(stock_ids, target_ids) -> list:
    """库存里有而目标玩家没有的成就 id (排序稳定)。

    只做减法 → 天然满足「只增不减」, 从不撤销目标玩家自己额外的成就。
    """
    return sorted(set(stock_ids) - set(target_ids))


def grant(target: str, adv_ids) -> tuple:
    """逐条下发 ``advancement grant <target> only <id>``。

    :return: (已下发条数, 异常条数)

    注意 MCDR 看不到命令执行结果, 「已下发」仅代表命令已交给服务端;
    单条异常不影响后续条目。``grant_interval`` 用于限速。
    """
    interval = my_lib.get_grant_interval()
    sent = 0
    failed = 0
    for adv_id in adv_ids:
        try:
            my_lib.plugin_server.execute(f"advancement grant {target} only {adv_id}")
            sent += 1
        except Exception as e:
            failed += 1
            my_lib._log(f"[AdvMaple] 下发 grant 失败 ({target} {adv_id}): {e}")
        if interval > 0:
            time.sleep(interval)
    return sent, failed


def clear_cache():
    """清空内部缓存 (配置重载后调用)"""
    _usercache_cache.update({"mtime": None, "path": None, "by_name": {}})
