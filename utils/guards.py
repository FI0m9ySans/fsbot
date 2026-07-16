"""
FSBot Guards - 权限检查与安全机制
"""

import discord

# ── 权限常量 ──
OWNER_ID = 1516859801790054532
ADMIN_ROLE_ID = 1517070447173435473

# ── ServerKing 全局锁 ──
_lockdown_mode = False

def get_lockdown_mode():
    return _lockdown_mode

def set_lockdown_mode(mode: bool):
    global _lockdown_mode
    _lockdown_mode = mode

def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID

def is_admin(interaction: discord.Interaction) -> bool:
    """检查用户是否为管理员（拥有 ADMIN_ROLE_ID 身份组）"""
    if is_owner(interaction):
        return True
    role = interaction.guild.get_role(ADMIN_ROLE_ID) if interaction.guild else None
    return role is not None and role in interaction.user.roles
