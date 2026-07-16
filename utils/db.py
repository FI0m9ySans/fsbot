"""
FSBot Database Layer
SQLite WAL mode, thread-safe via check_same_thread=False
"""

import sqlite3
import math as _math
from datetime import datetime, timedelta

# ── 数据库连接 ──
conn = sqlite3.connect('users.db', timeout=10)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')
cursor = conn.cursor()

# ── 初始化表结构 ──
def _init_tables():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            last_daily TEXT,
            exp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0
        )
    ''')
    conn.commit()

    # 兼容旧表：添加 exp 和 level 列
    for col in ['exp', 'level']:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # 兼容旧表：添加天赋列
    for col in ['talent_power', 'talent_luck', 'talent_diligence', 'talent_wisdom']:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # 兼容旧表：添加 monthly_points 列
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN monthly_points INTEGER DEFAULT 0")
        conn.commit()
        cursor.execute("UPDATE users SET monthly_points = points WHERE monthly_points = 0")
        conn.commit()
        print("[DB] 已添加 monthly_points 列并迁移现有积分数据")
    except sqlite3.OperationalError:
        pass

    # 兼容旧表：添加 daily_checkin_time 列（S1 每日签到时间排行榜）
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN daily_checkin_time TEXT")
        conn.commit()
        print("[DB] 已添加 daily_checkin_time 列")
    except sqlite3.OperationalError:
        pass

    # 兼容旧表：添加 best_luck_count 列（S1 手气最佳排行）
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN best_luck_count INTEGER DEFAULT 0")
        conn.commit()
        print("[DB] 已添加 best_luck_count 列")
    except sqlite3.OperationalError:
        pass

    # bot_meta 表（持久化关键状态）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()

_init_tables()

# ── bot_meta 工具 ──
def get_meta(key, default=None):
    cursor.execute("SELECT value FROM bot_meta WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_meta(key, value):
    cursor.execute("INSERT OR REPLACE INTO bot_meta (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

# ── 用户操作 ──
def get_or_create_user(user_id, username):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, username, points, last_daily, exp, level, "
            "talent_power, talent_luck, talent_diligence, talent_wisdom, monthly_points) "
            "VALUES (?, ?, 0, NULL, 0, 0, 0, 0, 0, 0, 0)",
            (user_id, username)
        )
        conn.commit()
        return (user_id, username, 0, None, 0, 0, 0, 0, 0, 0, 0)
    while len(user) < 11:
        user = user + (0,)
    return user

def update_user_points(user_id, points, last_daily):
    """签到用：同时更新永久和月度积分"""
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    old = cursor.fetchone()
    delta = points - (old[0] if old else 0)
    cursor.execute(
        "UPDATE users SET points = ?, monthly_points = monthly_points + ?, last_daily = ? WHERE user_id = ?",
        (points, delta, last_daily, user_id)
    )
    conn.commit()

# ── 经验/等级系统 ──
def exp_to_level(total_exp):
    if total_exp <= 0:
        return 0
    return int((_math.sqrt(1 + 8 * total_exp / 100) - 1) / 2)

def level_to_exp_required(level):
    return 100 * (level + 1) * (level + 2) // 2

def add_exp(user_id, amount):
    cursor.execute("SELECT exp, level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False, 0, 0
    exp, level = row
    new_exp = exp + amount
    new_level = exp_to_level(new_exp)
    leveled_up = new_level > level
    cursor.execute("UPDATE users SET exp = ?, level = ? WHERE user_id = ?", (new_exp, new_level, user_id))
    conn.commit()
    return leveled_up, new_level, new_exp

# ── 积分操作 ──
def deduct_points(user_id, amount):
    """扣除永久积分（商店/天赋用），不扣月度积分"""
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False, 0
    current = row[0]
    if current < amount:
        return False, current
    new_points = current - amount
    cursor.execute("UPDATE users SET points = ? WHERE user_id = ?", (new_points, user_id))
    conn.commit()
    return True, new_points

def add_points(user_id, amount):
    """增加积分：同时加到永久和月度积分"""
    get_or_create_user(user_id, 'unknown')
    cursor.execute(
        "UPDATE users SET points = points + ?, monthly_points = monthly_points + ? WHERE user_id = ?",
        (amount, amount, user_id)
    )
    conn.commit()
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_permanent_points(user_id, amount):
    """仅加永久积分（转账接收方、月度奖励等，不加月度）"""
    get_or_create_user(user_id, 'unknown')
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

# ── 天赋 ──
def get_talents(user_id):
    cursor.execute(
        "SELECT talent_power, talent_luck, talent_diligence, talent_wisdom FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        return (0, 0, 0, 0)
    return row


# ── 每日签到时间 (S1 排行榜) ──
def record_daily_checkin(user_id, username, iso_time):
    """记录今日签到时间戳（用于 Dashboard 每日签到排行榜）"""
    get_or_create_user(user_id, username)
    cursor.execute(
        "UPDATE users SET daily_checkin_time = ? WHERE user_id = ?",
        (iso_time, user_id)
    )
    conn.commit()

def get_daily_checkin_ranking(today_date, limit=50):
    """获取今日签到排行榜：按签到时间升序（最早签到排第一）"""
    cursor.execute(
        "SELECT user_id, username, daily_checkin_time FROM users "
        "WHERE daily_checkin_time LIKE ? "
        "ORDER BY daily_checkin_time ASC LIMIT ?",
        (today_date + '%', limit)
    )
    rows = cursor.fetchall()
    result = []
    for i, row in enumerate(rows, 1):
        result.append({
            "rank": i,
            "user_id": row[0],
            "username": row[1],
            "checkin_time": row[2]
        })
    return result


# ── 红包系统 (S1 麦收季) ──
def _init_red_packets_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS red_packets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id TEXT NOT NULL,
            creator_name TEXT,
            total_amount INTEGER NOT NULL,
            count INTEGER NOT NULL,
            amounts TEXT NOT NULL,
            remaining_count INTEGER NOT NULL,
            message TEXT DEFAULT '',
            claimed_by TEXT DEFAULT '[]',
            channel_id TEXT,
            message_id TEXT,
            created_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    conn.commit()

_init_red_packets_table()

def create_red_packet(creator_id, creator_name, total_amount, count, message, channel_id=None, message_id=None):
    """创建红包，返回 rp_id"""
    import random, json
    # 二倍均值法预拆分
    amounts = []
    remaining = total_amount
    for i in range(count - 1, 0, -1):
        max_val = max(remaining // (i + 1) * 2, 1)
        amt = random.randint(1, max_val)
        amounts.append(amt)
        remaining -= amt
    amounts.append(remaining)
    random.shuffle(amounts)  # 打乱顺序

    now = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    expires = (datetime.now() + timedelta(hours=8) + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute(
        'INSERT INTO red_packets (creator_id, creator_name, total_amount, count, amounts, remaining_count, message, channel_id, message_id, created_at, expires_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (creator_id, creator_name, total_amount, count, json.dumps(amounts), count, message, channel_id, message_id, now, expires, 'active')
    )
    conn.commit()
    return cursor.lastrowid

def claim_red_packet(rp_id, user_id, username):
    """领取红包，返回 (success: bool, amount: int, msg: str)"""
    import json
    cursor.execute(
        'SELECT creator_id, total_amount, count, amounts, remaining_count, claimed_by, status, expires_at FROM red_packets WHERE id = ?',
        (rp_id,)
    )
    row = cursor.fetchone()
    if not row:
        return False, 0, "红包不存在"
    
    creator_id, total_amount, count, amounts_json, remaining_count, claimed_json, status, expires_at = row

    if user_id == creator_id:
        return False, 0, "不能抢自己的红包"

    if status != 'active':
        return False, 0, "红包已过期或已被抢完"
    
    claimed = json.loads(claimed_json) if claimed_json else []
    claimed_ids = [c['user_id'] for c in claimed]
    
    if user_id in claimed_ids:
        for c in claimed:
            if c['user_id'] == user_id:
                return False, c['amount'], f"你已经抢过这个红包了（+{c['amount']} 积分）"
    
    amounts = json.loads(amounts_json)
    # 按顺序取：已抢 count - remaining_count 个
    idx = count - remaining_count
    if idx >= len(amounts):
        return False, 0, "红包已被抢完"
    
    amount = amounts[idx]
    claimed.append({"user_id": user_id, "username": username, "amount": amount})
    remaining_count -= 1

    new_status = 'finished' if remaining_count == 0 else 'active'

    # 如果是最后一个，记录手气最佳
    if remaining_count == 0:
        max_amount = max(c['amount'] for c in claimed)
        for c in claimed:
            if c['amount'] == max_amount:
                cursor.execute(
                    "UPDATE users SET best_luck_count = best_luck_count + 1 WHERE user_id = ?",
                    (c['user_id'],)
                )
                # 确保用户存在
                get_or_create_user(c['user_id'], c['username'])

    cursor.execute(
        'UPDATE red_packets SET remaining_count = ?, claimed_by = ?, status = ? WHERE id = ?',
        (remaining_count, json.dumps(claimed, ensure_ascii=False), new_status, rp_id)
    )
    conn.commit()
    return True, amount, f"🎉 抢到了 {amount} 积分！"

def get_red_packet(rp_id):
    """获取红包完整信息"""
    import json
    cursor.execute('SELECT * FROM red_packets WHERE id = ?', (rp_id,))
    row = cursor.fetchone()
    if not row:
        return None
    cols = ['id', 'creator_id', 'creator_name', 'total_amount', 'count', 'amounts',
            'remaining_count', 'message', 'claimed_by', 'channel_id', 'message_id',
            'created_at', 'expires_at', 'status']
    data = dict(zip(cols, row))
    data['claimed_by'] = json.loads(data['claimed_by']) if data['claimed_by'] else []
    return data

def update_red_packet_message(rp_id, channel_id, message_id):
    """更新红包消息ID"""
    cursor.execute('UPDATE red_packets SET channel_id = ?, message_id = ? WHERE id = ?',
                   (str(channel_id) if channel_id else None, str(message_id) if message_id else None, rp_id))
    conn.commit()

def expire_red_packets():
    """检查并过期红包，返回需要退款的列表 [(rp_id, creator_id, remaining_amount)]"""
    import json
    now = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "SELECT id, creator_id, amounts, remaining_count, claimed_by FROM red_packets WHERE status = 'active' AND expires_at < ?",
        (now,)
    )
    rows = cursor.fetchall()
    refunds = []
    for row in rows:
        rp_id, creator_id, amounts_json, remaining_count, claimed_json = row
        amounts = json.loads(amounts_json) if amounts_json else []
        claimed = json.loads(claimed_json) if claimed_json else []
        # 计算剩余金额
        claimed_total = sum(c['amount'] for c in claimed)
        remaining = sum(amounts) - claimed_total
        if remaining > 0:
            refunds.append((rp_id, creator_id, remaining))
        cursor.execute("UPDATE red_packets SET status = 'expired' WHERE id = ?", (rp_id,))
    if refunds:
        conn.commit()
    return refunds

def get_best_luck_ranking(limit=50):
    """获取手气最佳排行榜：按最佳次数降序"""
    cursor.execute(
        "SELECT user_id, username, best_luck_count FROM users "
        "WHERE best_luck_count > 0 "
        "ORDER BY best_luck_count DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    result = []
    for i, row in enumerate(rows, 1):
        result.append({
            "rank": i,
            "user_id": row[0],
            "username": row[1] if row[1] else f"User_{row[0]}",
            "best_luck_count": row[2]
        })
    return result
