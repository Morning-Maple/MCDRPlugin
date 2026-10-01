"""
pagination.py — 通用分页组件

把「算总页数 → 夹取页码 → 切片 → 渲染标题与翻页栏」这套列表命令都要写的逻辑
收敛为 Paginator, 供 home / warp 等任何列表类命令复用。

业务侧典型写法:
    pg = Paginator(list(items), page_size, page)
    if pg.empty:
        ...
        return
    source.reply(pg.header("已设置的家列表", cap=my_lib.get_sethome_max()))
    for name, info in pg.items:
        ...
    if pg.max_page > 1:
        source.reply(pg.controls(f"{my_lib.cmd('home')} list"))
"""
from typing import Any, List, Sequence, Tuple

from mcdreforged.api.rtext import RText, RTextList, RColor

from . import my_lib


class Paginator:
    """通用分页器: 越界页码自动夹取到 [1, max_page], 无需调用方判断。"""

    def __init__(self, items: Sequence[Any], page_size: int, page: int = 1):
        self._items: List[Any] = list(items)
        self.page_size: int = max(1, page_size)
        self.total: int = len(self._items)
        # 向上取整; total 为 0 时仍为 1 页, 避免出现「第 1/0 页」
        self.max_page: int = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page: int = max(1, min(int(page), self.max_page))

    @property
    def empty(self) -> bool:
        """数据是否为空 (与页码无关)"""
        return self.total == 0

    @property
    def start_index(self) -> int:
        """当前页第一条在全集中的下标 (0 起)"""
        return (self.page - 1) * self.page_size

    @property
    def items(self) -> List[Any]:
        """当前页的数据切片"""
        return self._items[self.start_index:self.start_index + self.page_size]

    def indexed(self) -> List[Tuple[int, Any]]:
        """当前页数据 + 全局序号 (1 起), 形如 [(1, item), (2, item), ...]"""
        return [(self.start_index + i + 1, item) for i, item in enumerate(self.items)]

    def header(self, title: str, cap: int = None) -> str:
        """列表标题行, 形如 '§6已设置的家列表 (3/10)  §7第 1/1 页'。

        :param cap: 数量上限; 提供时标题显示 '总数/上限', 否则只显示总数
        """
        total_desc = f"{self.total}/{cap}" if cap is not None else str(self.total)
        return f"{my_lib.TAG}§6{title} ({total_desc})  §7第 {self.page}/{self.max_page} 页"

    def controls(self, base_cmd: str) -> RTextList:
        """底部可点击翻页栏: [上一页] X/Y [下一页]

        :param base_cmd: 翻页命令前缀 (不含页码), 如 '!!mhome list'
        """
        click_action = my_lib.get_click_action()
        parts = ["  "]
        if self.page > 1:
            prev_cmd = f"{base_cmd} {self.page - 1}"
            parts.append(
                RText("[上一页]", color=RColor.aqua).c(click_action, prev_cmd).h(prev_cmd)
            )
        else:
            parts.append(RText("[上一页]", color=RColor.dark_gray))  # 已是首页, 不可点
        parts.append(f" §7{self.page}/{self.max_page} ")
        if self.page < self.max_page:
            next_cmd = f"{base_cmd} {self.page + 1}"
            parts.append(
                RText("[下一页]", color=RColor.aqua).c(click_action, next_cmd).h(next_cmd)
            )
        else:
            parts.append(RText("[下一页]", color=RColor.dark_gray))  # 已是末页, 不可点
        return RTextList(*parts)
