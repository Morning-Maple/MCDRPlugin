"""
cooldown.py — 冷却时间管理工具类

按 (key, feature) 记录上次使用时间戳, key 通常为玩家 UUID, feature 为功能名。
不持久化, 随插件重载/重启清零。
"""
import time


class CooldownManager:
    """管理各功能的独立冷却"""

    def __init__(self):
        # _records[key][feature] = 上次使用时间戳
        self._records: dict[str, dict[str, float]] = {}

    def check(self, key: str, feature: str, cd_seconds: float) -> int:
        """检查冷却, 返回剩余秒数 (向上取整); 0 表示可用。

        :param cd_seconds: 该功能的冷却秒数, <= 0 表示无冷却
        """
        if cd_seconds <= 0:
            return 0
        last = self._records.get(key, {}).get(feature, 0)
        remain = cd_seconds - (time.time() - last)
        return max(0, int(remain) + (1 if remain % 1 > 0 else 0))

    def record(self, key: str, feature: str):
        """记录本次使用时间戳"""
        self._records.setdefault(key, {})[feature] = time.time()

    def reset(self, key: str, feature: str = None):
        """清除冷却记录 (如传送失败需退还冷却时使用)。

        feature 为 None 时清除该 key 下所有功能的记录。
        """
        if feature is None:
            self._records.pop(key, None)
        elif key in self._records:
            self._records[key].pop(feature, None)
