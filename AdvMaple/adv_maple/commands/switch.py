"""
switch.py — 自助同步开关管理

!!madv switch          查看开关状态
!!madv switch on       开启 (权限 3)
!!madv switch off      关闭 (权限 3)

开关落在配置文件 allow_self_sync, 修改后立即写回文件并即时生效,
不需要重载插件 —— 因为它是运行时读取的普通配置项, 不涉及命令树。
"""
import mcdreforged as mcdr

from .. import my_lib
from ..my_lib import TAG


def _state_desc(enabled: bool) -> str:
    """开关状态的彩色描述 (自带「已」字, 拼接时不要再加)"""
    return "§a已开启" if enabled else "§c已关闭"


def _notify_change(source: mcdr.CommandSource, enabled: bool):
    """统一的变更结果回复"""
    if my_lib.set_self_sync_allowed(enabled):
        source.reply(
            f"{TAG}§a自助同步开关{_state_desc(enabled)}"
            f"\n§7  现在普通玩家§f{'可以' if enabled else '不能'}§7用 "
            f"§f{my_lib.cmd('adv')} self §7给自己补齐成就"
        )
    else:
        source.reply(
            f"{TAG}§e开关已在内存中{_state_desc(enabled)}, 但写回配置文件失败"
            f"\n§7  重启后会恢复原值, 请检查日志"
        )
    my_lib._log(
        f"[AdvMaple] 自助同步开关被 {source} 设为 {'on' if enabled else 'off'}"
    )


# ============================================================
# !!madv switch
# ============================================================

def show_switch(source: mcdr.CommandSource):
    """!!madv switch — 查看自助同步开关状态"""
    enabled = my_lib.is_self_sync_allowed()
    usage = (
        f"§7  普通玩家可以使用 §f{my_lib.cmd('adv')} self §7给自己补齐成就"
        if enabled else
        f"§7  普通玩家暂时无法使用 §f{my_lib.cmd('adv')} self"
    )
    source.reply(
        f"{TAG}§6自助同步开关: {_state_desc(enabled)}"
        f"\n{usage} §8(该命令权限: {my_lib.get_perm('self')})"
        f"\n§8  调整: {my_lib.cmd('adv')} switch on | off"
    )


# ============================================================
# !!madv switch on / off
# ============================================================

@mcdr.new_thread("AdvMaple-switch")
def turn_on(source: mcdr.CommandSource):
    """!!madv switch on — 开启自助同步"""
    _notify_change(source, True)


@mcdr.new_thread("AdvMaple-switch")
def turn_off(source: mcdr.CommandSource):
    """!!madv switch off — 关闭自助同步"""
    _notify_change(source, False)
