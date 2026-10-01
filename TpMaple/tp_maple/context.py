"""
context.py — 玩家命令上下文 (样板收敛)

统一处理「该命令只能由玩家执行」与「无法获取玩家 UUID」两块样板,
并把 (玩家名 / UUID / 命令源) 打包成 PlayerContext, 供传送服务与业务命令共用。

业务命令统一写法:
    ctx = resolve_player(source)
    if ctx is None:
        return          # 失败信息已由这里回复, 业务直接返回
    ctx.reply(...)
"""
from dataclasses import dataclass
from typing import Optional

import mcdreforged as mcdr

from . import my_lib

# 统一的失败提示文案 (字面与旧实现保持一致)
MSG_NOT_PLAYER = f"{my_lib.TAG}§c该命令只能由玩家执行"
MSG_NO_UUID = f"{my_lib.TAG}§c无法获取你的 UUID"


@dataclass(frozen=True)
class PlayerContext:
    """一次玩家命令的上下文: 已校验的玩家名 + 命令源 (+ 可选 UUID)"""

    name: str
    source: mcdr.CommandSource
    uuid: Optional[str] = None

    def reply(self, msg):
        """向该玩家回复一条消息 (支持 § 颜色码与 RText)"""
        self.source.reply(msg)


def resolve_player(source: mcdr.CommandSource, *, need_uuid: bool = True) -> Optional[PlayerContext]:
    """解析玩家命令源为 PlayerContext。

    失败时 (非玩家执行 / 取不到 UUID) 已回复错误信息并返回 None, 调用方直接 return 即可。

    :param need_uuid: 是否需要玩家 UUID (如家/地标数据以 UUID 为键时传 True);
                      仅需玩家名与位置时传 False, 可省去一次 API 查询。
    """
    if not getattr(source, "is_player", False):
        source.reply(MSG_NOT_PLAYER)
        return None

    player_name = source.player
    if not need_uuid:
        return PlayerContext(name=player_name, source=source)

    player_uuid = my_lib.get_player_uuid(player_name)
    if player_uuid is None:
        source.reply(MSG_NO_UUID)
        return None

    return PlayerContext(name=player_name, source=source, uuid=player_uuid)
