"""
mod_sdk.py — FSBot 模组扩展 SDK
为模组创作者提供：多货币、物品系统、商店、红包、储物袋、工具等。

依赖：main.py 中已有的 discord, sqlite3, cursor, conn, bot, app_commands
用法：在 main.py 末尾 import mod_sdk 并调用 init_mod_sdk()
"""

import json
import random
import time
import traceback
import asyncio
from datetime import datetime, timedelta

# ── 引用 main 中的全局对象（由 init_mod_sdk 注入） ──
_cursor = None
_conn = None
_bot = None

# ── 内存缓存 ──
_custom_currencies = {}   # {currency_id: {name, symbol, guild_id, ...}}
_items_def = {}            # {item_id: {name, item_type, properties, ...}}
_shops = {}               # {shop_id: {...}}
_red_packets = {}         # {rp_id: {...}}
_custom_channel_ids = {}   # {mod_name: [channel]}
_custom_role_ids = {}      # {mod_name: [roles]}
_mod_dependencies = {}     # {mod_name: {'requires': [..], 'optional': [..]}}


def init_mod_sdk(cursor, conn, bot):
    """在 main.py 的 on_ready 中调用，注入全局对象并建表"""
    global _cursor, _conn, _bot
    _cursor = cursor
    _conn = conn
    _bot = bot
    _create_tables()
    _load_cache_from_db()
    print("[ModSDK] 扩展 SDK 初始化完成")


def _create_tables():
    """创建所有扩展功能所需的数据库表"""
    try:
        # 1. 自定义货币表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_currencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT NOT NULL,
                name TEXT NOT NULL,
                symbol TEXT DEFAULT '',
                description TEXT DEFAULT '',
                earn_methods TEXT DEFAULT '[]',   -- JSON 数组
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 2. 用户自定义货币余额
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_user_currencies (
                user_id INTEGER NOT NULL,
                currency_id INTEGER NOT NULL,
                amount REAL DEFAULT 0,
                PRIMARY KEY (user_id, currency_id),
                FOREIGN KEY (currency_id) REFERENCES sdk_currencies(id)
            )
        ''')
        # 3. 物品定义表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                item_type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',  -- JSON
                transferable BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 4. 用户库存表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_inventory (
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                instance_props TEXT DEFAULT '{}',  -- JSON 实例属性
                PRIMARY KEY (user_id, item_id),
                FOREIGN KEY (item_id) REFERENCES sdk_items(id)
            )
        ''')
        # 5. 储物袋表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_storage_bags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mod_name TEXT,
                name TEXT NOT NULL,
                capacity INTEGER DEFAULT 20,
                items_json TEXT DEFAULT '[]',  -- JSON 数组
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 6. 商店表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_shops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 7. 商店商品表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                item_id INTEGER,
                price REAL NOT NULL,
                currency_type TEXT DEFAULT 'points',
                currency_id INTEGER,
                quantity INTEGER DEFAULT -1,
                FOREIGN KEY (shop_id) REFERENCES sdk_shops(id),
                FOREIGN KEY (item_id) REFERENCES sdk_items(id),
                FOREIGN KEY (currency_id) REFERENCES sdk_currencies(id)
            )
        ''')
        # 8. 红包表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_red_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                total_amount REAL NOT NULL,
                currency_type TEXT DEFAULT 'points',
                currency_id INTEGER,
                quantity INTEGER NOT NULL,
                remaining_quantity INTEGER NOT NULL,
                claimed_by TEXT DEFAULT '[]',  -- JSON 数组
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (currency_id) REFERENCES sdk_currencies(id)
            )
        ''')
        # 9. 记事本表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mod_name TEXT,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 10. 计算器历史表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_calc_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                expression TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 11. 待办事项表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mod_name TEXT,
                task TEXT NOT NULL,
                completed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        # 12. 模组依赖表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_mod_deps (
                mod_name TEXT NOT NULL,
                depends_on TEXT NOT NULL,
                dep_type TEXT DEFAULT 'requires',
                PRIMARY KEY (mod_name, depends_on)
            )
        ''')
        # 13. 自定义频道ID表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_custom_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 14. 自定义身份组ID表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_custom_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_name TEXT NOT NULL,
                role_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 15. 模组自定义游戏记录表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_custom_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT NOT NULL,
                game_name TEXT NOT NULL,
                player1_id INTEGER,
                player2_id INTEGER,
                currency_type TEXT DEFAULT 'points',
                currency_id INTEGER,
                bet_amount REAL DEFAULT 0,
                winner_id INTEGER,
                game_data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (currency_id) REFERENCES sdk_currencies(id)
            )
        ''')
        # 16. 市场/拍卖行表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_market (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT,
                seller_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                price REAL NOT NULL,
                currency_type TEXT DEFAULT 'points',
                currency_id INTEGER,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES sdk_items(id),
                FOREIGN KEY (currency_id) REFERENCES sdk_currencies(id)
            )
        ''')
        # 17. 市场交易记录表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_market_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                total_price REAL NOT NULL,
                currency_type TEXT DEFAULT 'points',
                currency_id INTEGER,
                transaction_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (market_id) REFERENCES sdk_market(id)
            )
        ''')
        # 18. 公会系统 - 公会表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_guilds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                funds REAL DEFAULT 0,
                leader_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 19. 公会系统 - 成员表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_guild_members (
                guild_id TEXT NOT NULL,
                sdk_guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                contribute_exp INTEGER DEFAULT 0,
                join_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (sdk_guild_id, user_id),
                FOREIGN KEY (sdk_guild_id) REFERENCES sdk_guilds(id)
            )
        ''')
        # 20. 公会系统 - 仓库表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_guild_storage (
                sdk_guild_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (sdk_guild_id, item_id),
                FOREIGN KEY (sdk_guild_id) REFERENCES sdk_guilds(id),
                FOREIGN KEY (item_id) REFERENCES sdk_items(id)
            )
        ''')
        # 21. 资料库系统 - 页面表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_wiki_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                author_id INTEGER NOT NULL,
                category TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 21b. 资料库系统 - 版本历史表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_wiki_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                version_num INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                category TEXT DEFAULT '',
                editor_id INTEGER NOT NULL,
                edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(page_id, version_num),
                FOREIGN KEY (page_id) REFERENCES sdk_wiki_pages(id)
            )
        ''')
        # 22. 自动化系统 - 规则表
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_automations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                mod_name TEXT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                trigger_type TEXT NOT NULL,
                trigger_config TEXT DEFAULT '{}',
                action_config TEXT DEFAULT '{}',
                enabled BOOLEAN DEFAULT 1,
                creator_id INTEGER NOT NULL,
                last_run_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 确保增益/装备表存在
        _ensure_buff_tables()
        _conn.commit()
        print("[ModSDK] 扩展数据库表创建/验证完成")
    except Exception as e:
        print(f"[ModSDK] 建表失败: {e}")
        traceback.print_exc()


def _load_cache_from_db():
    """从数据库加载缓存"""
    try:
        _cursor.execute('SELECT id, name, symbol, guild_id, mod_name FROM sdk_currencies')
        for row in _cursor.fetchall():
            _custom_currencies[row[0]] = {'id': row[0], 'name': row[1], 'symbol': row[2], 'guild_id': row[3], 'mod_name': row[4]}
        _cursor.execute('SELECT id, name, item_type, mod_name, transferable FROM sdk_items')
        for row in _cursor.fetchall():
            _items_def[row[0]] = {'id': row[0], 'name': row[1], 'item_type': row[2], 'mod_name': row[3], 'transferable': bool(row[4])}
        print(f"[ModSDK] 缓存加载: {len(_custom_currencies)} 货币, {len(_items_def)} 物品")
    except Exception as e:
        print(f"[ModSDK] 缓存加载失败: {e}")


# ═══════════════════════════════════════════
# 工具函数：获取用户积分（points）/ 修改积分
# ═══════════════════════════════════════════

def get_points(user_id):
    try:
        _cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
        row = _cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

def add_points(user_id, amount):
    try:
        _cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        if _cursor.fetchone():
            _cursor.execute(
                'UPDATE users SET points = points + ?, monthly_points = monthly_points + ? WHERE user_id = ?',
                (amount, amount, user_id)
            )
        else:
            _cursor.execute(
                'INSERT INTO users (user_id, points, monthly_points) VALUES (?, ?, ?)',
                (user_id, amount, amount)
            )
        _conn.commit()
        _cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
        return _cursor.fetchone()[0]
    except Exception as e:
        print(f"[ModSDK] add_points 失败: {e}")
        return 0


def remove_points(user_id, amount):
    """扣除积分（不低于0），仅扣永久积分，不影响月度积分"""
    try:
        _cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
        row = _cursor.fetchone()
        if row:
            new_points = max(0, row[0] - amount)
            _cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (new_points, user_id))
            _conn.commit()
            return new_points
        return 0
    except Exception as e:
        print(f"[ModSDK] remove_points 失败: {e}")
        return 0


def add_exp(user_id, amount):
    """增加经验值，自动重算等级"""
    import math
    try:
        _cursor.execute('SELECT exp, level FROM users WHERE user_id = ?', (user_id,))
        row = _cursor.fetchone()
        if row:
            exp, level = row
            new_exp = max(0, exp + amount)
            if new_exp <= 0:
                new_level = 0
            else:
                new_level = int((math.sqrt(1 + 8 * new_exp / 100) - 1) / 2)
            _cursor.execute('UPDATE users SET exp = ?, level = ? WHERE user_id = ?', (new_exp, new_level, user_id))
            _conn.commit()
            return new_exp
        else:
            # 用户不存在，创建
            if amount <= 0:
                new_level = 0
            else:
                new_level = int((math.sqrt(1 + 8 * amount / 100) - 1) / 2)
            _cursor.execute('INSERT INTO users (user_id, exp, level) VALUES (?, ?, ?)', (user_id, max(0, amount), new_level))
            _conn.commit()
            return max(0, amount)
    except Exception as e:
        print(f"[ModSDK] add_exp 失败: {e}")
        return 0


# ═══════════════════════════════════════════
# 1. 自定义货币系统
# ═══════════════════════════════════════════

def currency_create(guild_id, mod_name, name, symbol='', description='', earn_methods=None):
    """创建自定义货币。earn_methods 是 JSON 数组，格式：
       [{"type": "command", "command": "/daily", "amount": 100},
        {"type": "message", "amount": 1, "chance": 0.1},
        {"type": "exchange", "from_currency": "points", "rate": 10}]
       返回 (success, currency_id or error_msg)
    """
    try:
        em = json.dumps(earn_methods or [], ensure_ascii=False)
        _cursor.execute(
            'INSERT INTO sdk_currencies (guild_id, mod_name, name, symbol, description, earn_methods) VALUES (?,?,?,?,?,?)',
            (guild_id, mod_name, name, symbol, description, em)
        )
        _conn.commit()
        cid = _cursor.lastrowid
        _custom_currencies[cid] = {'id': cid, 'name': name, 'symbol': symbol, 'guild_id': guild_id, 'mod_name': mod_name}
        return True, cid
    except Exception as e:
        return False, str(e)

def currency_get_balance(user_id, currency_id):
    try:
        _cursor.execute('SELECT amount FROM sdk_user_currencies WHERE user_id = ? AND currency_id = ?', (user_id, currency_id))
        row = _cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

def currency_add(user_id, currency_id, amount):
    try:
        _cursor.execute('SELECT 1 FROM sdk_user_currencies WHERE user_id = ? AND currency_id = ?', (user_id, currency_id))
        if _cursor.fetchone():
            _cursor.execute('UPDATE sdk_user_currencies SET amount = amount + ? WHERE user_id = ? AND currency_id = ?', (amount, user_id, currency_id))
        else:
            _cursor.execute('INSERT INTO sdk_user_currencies (user_id, currency_id, amount) VALUES (?,?,?)', (user_id, currency_id, amount))
        _conn.commit()
        return True
    except Exception as e:
        print(f"[ModSDK] currency_add 失败: {e}")
        return False

def currency_transfer(from_user, to_user, currency_id, amount):
    """转账，返回 (success, msg)"""
    try:
        bal = currency_get_balance(from_user, currency_id)
        if bal < amount:
            return False, '余额不足'
        currency_add(from_user, currency_id, -amount)
        currency_add(to_user, currency_id, amount)
        return True, '转账成功'
    except Exception as e:
        return False, str(e)

def currency_exchange(user_id, from_type, from_id, to_currency_id, rate):
    """兑换：from_type='points' 或 'currency'，from_id 是对应的 ID 或 None（points 用 None）"""
    try:
        if from_type == 'points':
            pts = get_points(user_id)
            cost = int(to_currency_id * rate)  # to_currency_id 这里复用为数量
            if pts < cost:
                return False, '积分不足'
            add_points(user_id, -cost)
            currency_add(user_id, to_currency_id, to_currency_id)  # 这里 to_currency_id 复用，实际应该用独立参数
            return True, f'兑换成功，消耗 {cost} 积分'
        else:
            bal = currency_get_balance(user_id, from_id)
            if bal < rate:
                return False, '余额不足'
            currency_add(user_id, from_id, -rate)
            currency_add(user_id, to_currency_id, 1)
            return True, '兑换成功'
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# 7/8/9/13/14. 物品与储物系统
# ═══════════════════════════════════════════

def item_create(guild_id, mod_name, name, item_type, description='', properties=None, transferable=True):
    """创建物品定义。item_type: box/weapon/food/buff/tool/container/custom
       properties: JSON 字典，如 {"damage": 10, "durability": 100}
    """
    try:
        props = json.dumps(properties or {}, ensure_ascii=False)
        _cursor.execute(
            'INSERT INTO sdk_items (guild_id, mod_name, name, description, item_type, properties, transferable) VALUES (?,?,?,?,?,?,?)',
            (guild_id, mod_name, name, description, item_type, props, 1 if transferable else 0)
        )
        _conn.commit()
        iid = _cursor.lastrowid
        _items_def[iid] = {'id': iid, 'name': name, 'item_type': item_type, 'mod_name': mod_name, 'transferable': transferable}
        return True, iid
    except Exception as e:
        return False, str(e)

def item_give(user_id, item_id, quantity=1, instance_props=None):
    try:
        ip = json.dumps(instance_props or {}, ensure_ascii=False)
        _cursor.execute('SELECT 1 FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        if _cursor.fetchone():
            _cursor.execute('UPDATE sdk_inventory SET quantity = quantity + ? WHERE user_id = ? AND item_id = ?', (quantity, user_id, item_id))
        else:
            _cursor.execute('INSERT INTO sdk_inventory (user_id, item_id, quantity, instance_props) VALUES (?,?,?,?)', (user_id, item_id, quantity, ip))
        _conn.commit()
        return True
    except Exception as e:
        print(f"[ModSDK] item_give 失败: {e}")
        return False

def item_take(user_id, item_id, quantity=1):
    try:
        _cursor.execute('SELECT quantity FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        row = _cursor.fetchone()
        if not row or row[0] < quantity:
            return False, '物品不足'
        new_q = row[0] - quantity
        if new_q <= 0:
            _cursor.execute('DELETE FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        else:
            _cursor.execute('UPDATE sdk_inventory SET quantity = ? WHERE user_id = ? AND item_id = ?', (new_q, user_id, item_id))
        _conn.commit()
        return True, '移除成功'
    except Exception as e:
        return False, str(e)

def item_transfer(from_user, to_user, item_id, quantity=1):
    """转交物品，检查物品是否可转交"""
    try:
        item_info = _items_def.get(item_id)
        if item_info and not item_info.get('transferable', True):
            return False, '该物品不可转交'
        ok, msg = item_take(from_user, item_id, quantity)
        if not ok:
            return False, msg
        item_give(to_user, item_id, quantity)
        return True, '转交成功'
    except Exception as e:
        return False, str(e)

def storage_bag_create(user_id, mod_name, name, capacity=20):
    try:
        _cursor.execute(
            'INSERT INTO sdk_storage_bags (user_id, mod_name, name, capacity, items_json) VALUES (?,?,?,?,?)',
            (user_id, mod_name, name, capacity, '[]')
        )
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def storage_bag_put(bag_id, item_id, quantity=1, instance_props=None):
    """往储物袋放入物品"""
    try:
        _cursor.execute('SELECT items_json, capacity FROM sdk_storage_bags WHERE id = ?', (bag_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '储物袋不存在'
        items = json.loads(row[0])
        if len(items) >= row[1]:
            return False, '储物袋已满'
        items.append({'item_id': item_id, 'quantity': quantity, 'props': instance_props or {}})
        _cursor.execute('UPDATE sdk_storage_bags SET items_json = ? WHERE id = ?', (json.dumps(items, ensure_ascii=False), bag_id))
        _conn.commit()
        return True, '放入成功'
    except Exception as e:
        return False, str(e)

def storage_bag_take(bag_id, index, quantity=1):
    """从储物袋取出物品，index 是 items 数组下标"""
    try:
        _cursor.execute('SELECT items_json FROM sdk_storage_bags WHERE id = ?', (bag_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '储物袋不存在'
        items = json.loads(row[0])
        if index >= len(items):
            return False, '索引无效'
        entry = items[index]
        entry['quantity'] -= quantity
        if entry['quantity'] <= 0:
            items.pop(index)
        else:
            items[index] = entry
        _cursor.execute('UPDATE sdk_storage_bags SET items_json = ? WHERE id = ?', (json.dumps(items, ensure_ascii=False), bag_id))
        _conn.commit()
        return True, ('取出成功', entry)
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# 功能2. 模组自定义游戏
# ═══════════════════════════════════════════

def custom_game_create(guild_id, mod_name, game_name, player1_id, player2_id, currency_type='points', currency_id=None, bet_amount=0):
    try:
        _cursor.execute(
            'INSERT INTO sdk_custom_games (guild_id, mod_name, game_name, player1_id, player2_id, currency_type, currency_id, bet_amount) VALUES (?,?,?,?,?,?,?,?)',
            (guild_id, mod_name, game_name, player1_id, player2_id, currency_type, currency_id, bet_amount)
        )
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def custom_game_finish(game_id, winner_id):
    """结束游戏，发放奖励（赢家获得双方赌注）"""
    try:
        _cursor.execute('SELECT player1_id, player2_id, currency_type, currency_id, bet_amount FROM sdk_custom_games WHERE id = ?', (game_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '游戏不存在'
        p1, p2, ctype, cid, bet = row
        total_pot = bet * 2
        if ctype == 'points':
            add_points(winner_id, int(total_pot))
        else:
            currency_add(winner_id, cid, total_pot)
        _cursor.execute('UPDATE sdk_custom_games SET winner_id = ?, game_data = ? WHERE id = ?', (winner_id, json.dumps({'finished': True}, ensure_ascii=False), game_id))
        _conn.commit()
        return True, f'奖励 {total_pot} 已发放给赢家'
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# 功能3/4. 红包与群发
# ═══════════════════════════════════════════

def red_packet_create(guild_id, mod_name, creator_id, name, total_amount, currency_type='points', currency_id=None, quantity=1, description='', expire_hours=24):
    """创建红包，返回 (success, rp_id)"""
    try:
        expires = (datetime.now() + timedelta(hours=expire_hours)).strftime('%Y-%m-%d %H:%M:%S')
        _cursor.execute(
            'INSERT INTO sdk_red_packets (guild_id, mod_name, creator_id, name, description, total_amount, currency_type, currency_id, quantity, remaining_quantity, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (guild_id, mod_name, creator_id, name, description, total_amount, currency_type, currency_id, quantity, quantity, expires)
        )
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def red_packet_claim(rp_id, user_id):
    """领取红包，返回 (success, amount, msg)"""
    try:
        _cursor.execute('SELECT remaining_quantity, claimed_by, total_amount, currency_type, currency_id, creator_id, expires_at FROM sdk_red_packets WHERE id = ?', (rp_id,))
        row = _cursor.fetchone()
        if not row:
            return False, 0, '红包不存在'
        rem, claimed_raw, total, ctype, cid, creator, expires = row
        claimed = json.loads(claimed_raw)
        if user_id in claimed:
            return False, 0, '你已经领过了'
        if rem <= 0:
            return False, 0, '红包已被领完'
        # 检查过期
        if expires:
            try:
                exp_dt = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                if datetime.now() > exp_dt:
                    return False, 0, '红包已过期'
            except Exception:
                pass
        # 随机分配金额（简化：平均）
        amount = round(total / rem, 2)
        claimed.append(user_id)
        _cursor.execute('UPDATE sdk_red_packets SET remaining_quantity = remaining_quantity - 1, claimed_by = ? WHERE id = ?', (json.dumps(claimed, ensure_ascii=False), rp_id))
        # 发放
        if ctype == 'points':
            add_points(user_id, int(amount))
        else:
            currency_add(user_id, cid, amount)
        _conn.commit()
        return True, amount, f'领取了 {amount}'
    except Exception as e:
        return False, 0, str(e)

def currency_mass_send(guild_id, mod_name, currency_type, currency_id, amount_per_user, target_filter='all'):
    """群发货币。target_filter: 'all' / 'online' / role_id"""
    try:
        guild = _bot.get_guild(int(guild_id)) if guild_id else None
        if not guild:
            return False, '服务器不存在'
        members = [m for m in guild.members if not m.bot]
        if target_filter == 'online':
            members = [m for m in members if m.status != discord.Status.offline]
        count = 0
        for m in members:
            if currency_type == 'points':
                add_points(m.id, int(amount_per_user))
            else:
                currency_add(m.id, currency_id, amount_per_user)
            count += 1
        return True, f'已群发给 {count} 名成员'
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# 功能5/6. 自定义频道/身份组 ID
# ═══════════════════════════════════════════

def custom_channel_add(mod_name, channel_id, description=''):
    try:
        _cursor.execute('INSERT OR REPLACE INTO sdk_custom_channels (mod_name, channel_id, description) VALUES (?,?,?)', (mod_name, str(channel_id), description))
        _conn.commit()
        if mod_name not in _custom_channel_ids:
            _custom_channel_ids[mod_name] = []
        _custom_channel_ids[mod_name].append(str(channel_id))
        return True
    except Exception as e:
        return False, str(e)

def custom_role_add(mod_name, role_id, description=''):
    try:
        _cursor.execute('INSERT OR REPLACE INTO sdk_custom_roles (mod_name, role_id, description) VALUES (?,?,?)', (mod_name, str(role_id), description))
        _conn.commit()
        if mod_name not in _custom_role_ids:
            _custom_role_ids[mod_name] = []
        _custom_role_ids[mod_name].append(str(role_id))
        return True
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# 功能10/11/12. 记事本 / 计算器 / 待办
# ═══════════════════════════════════════════

def note_create(user_id, mod_name, title, content=''):
    try:
        _cursor.execute('INSERT INTO sdk_notes (user_id, mod_name, title, content) VALUES (?,?,?,?)', (user_id, mod_name, title, content))
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def note_list(user_id, mod_name=None):
    try:
        if mod_name:
            _cursor.execute('SELECT id, title, created_at FROM sdk_notes WHERE user_id = ? AND mod_name = ? ORDER BY created_at DESC', (user_id, mod_name))
        else:
            _cursor.execute('SELECT id, title, created_at FROM sdk_notes WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        return _cursor.fetchall()
    except Exception:
        return []

def calc_save(user_id, expression, result):
    try:
        _cursor.execute('INSERT INTO sdk_calc_history (user_id, expression, result) VALUES (?,?,?)', (user_id, expression, str(result)))
        _conn.commit()
        return True
    except Exception:
        return False

def todo_add(user_id, mod_name, task):
    try:
        _cursor.execute('INSERT INTO sdk_todos (user_id, mod_name, task) VALUES (?,?,?)', (user_id, mod_name, task))
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def todo_list(user_id, mod_name=None):
    try:
        if mod_name:
            _cursor.execute('SELECT id, task, completed FROM sdk_todos WHERE user_id = ? AND mod_name = ? ORDER BY completed, created_at', (user_id, mod_name))
        else:
            _cursor.execute('SELECT id, task, completed FROM sdk_todos WHERE user_id = ? ORDER BY completed, created_at', (user_id,))
        return _cursor.fetchall()
    except Exception:
        return []

def todo_complete(todo_id):
    try:
        _cursor.execute('UPDATE sdk_todos SET completed = 1, completed_at = ? WHERE id = ?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), todo_id))
        _conn.commit()
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════
# 功能15. 父子模组依赖
# ═══════════════════════════════════════════

def mod_dep_add(mod_name, depends_on, dep_type='requires'):
    try:
        _cursor.execute('INSERT OR REPLACE INTO sdk_mod_deps (mod_name, depends_on, dep_type) VALUES (?,?,?)', (mod_name, depends_on, dep_type))
        _conn.commit()
        if mod_name not in _mod_dependencies:
            _mod_dependencies[mod_name] = {'requires': [], 'optional': []}
        if dep_type == 'requires':
            if depends_on not in _mod_dependencies[mod_name]['requires']:
                _mod_dependencies[mod_name]['requires'].append(depends_on)
        else:
            if depends_on not in _mod_dependencies[mod_name]['optional']:
                _mod_dependencies[mod_name]['optional'].append(depends_on)
        return True
    except Exception as e:
        return False, str(e)

def mod_dep_check(mod_name):
    """检查依赖是否满足，返回 (ok, missing_list)"""
    deps = _mod_dependencies.get(mod_name, {'requires': [], 'optional': []})['requires']
    missing = []
    for d in deps:
        # 检查模组是否已加载（在 main 的 _loaded_mods 中）
        # 这里需要在 main.py 中调用时传入 _loaded_mods
        missing.append(d)  # 简化：先返回所有
    return len(missing) == 0, missing


# ═══════════════════════════════════════════
# 模组加载时解析扩展字段
# ═══════════════════════════════════════════

def load_mod_extensions(mod_data, guild_id=''):
    """解析模组 JSON 中的扩展字段，自动创建相应实体。
       返回 (success, msg)
    """
    mod_name = mod_data.get('name', 'unknown')
    guild_id = guild_id or str(mod_data.get('guild_id', ''))
    results = []

    # 1. currencies
    for c in mod_data.get('currencies', []):
        ok, res = currency_create(
            guild_id, mod_name, c['name'],
            symbol=c.get('symbol', ''),
            description=c.get('description', ''),
            earn_methods=c.get('earn_methods', [])
        )
        results.append(f'货币 "{c["name"]}": {"✅" if ok else "❌ "+str(res)}')

    # 2. items
    for it in mod_data.get('items', []):
        ok, res = item_create(
            guild_id, mod_name, it['name'], it['type'],
            description=it.get('description', ''),
            properties=it.get('properties', {}),
            transferable=it.get('transferable', True)
        )
        results.append(f'物品 "{it["name"]}": {"✅" if ok else "❌ "+str(res)}')

    # 3. shops
    for sh in mod_data.get('shops', []):
        try:
            _cursor.execute(
                'INSERT INTO sdk_shops (guild_id, mod_name, name, description) VALUES (?,?,?,?)',
                (guild_id, mod_name, sh['name'], sh.get('description', ''))
            )
            _conn.commit()
            shop_id = _cursor.lastrowid
            for si in sh.get('items', []):
                _cursor.execute(
                    'INSERT INTO sdk_shop_items (shop_id, item_id, price, currency_type, currency_id) VALUES (?,?,?,?,?)',
                    (shop_id, si.get('item_id'), si.get('price', 0), si.get('currency_type', 'points'), si.get('currency_id'))
                )
            _conn.commit()
            results.append(f'商店 "{sh["name"]}": ✅')
        except Exception as e:
            results.append(f'商店 "{sh.get("name","?")}": ❌ {e}')

    # 4. red_packets (预定义模板）
    for rp in mod_data.get('red_packets', []):
        results.append(f'红包模板 "{rp.get("name","?")}": 已记录（需用命令创建实例）')

    # 5. custom_channels
    for cc in mod_data.get('custom_channels', []):
        ok = custom_channel_add(mod_name, cc['channel_id'], cc.get('description', ''))
        results.append(f'自定义频道 {cc.get("channel_id")}: {"✅" if ok else "❌"}')

    # 6. custom_roles
    for cr in mod_data.get('custom_roles', []):
        ok = custom_role_add(mod_name, cr['role_id'], cr.get('description', ''))
        results.append(f'自定义身份组 {cr.get("role_id")}: {"✅" if ok else "❌"}')

    # 7. mod_deps
    for dep in mod_data.get('dependencies', []):
        mod_dep_add(mod_name, dep['name'], dep.get('type', 'requires'))
        results.append(f'依赖 "{dep["name"]}": 已记录')

    return True, '\n'.join(results) if results else '(无扩展功能)'






# ═══════════════════════════════════════════
# 17. 公会系统（简化版）
# ═══════════════════════════════════════════

def guild_create(guild_id, mod_name, name, description='', leader_id=0):
    try:
        _cursor.execute('SELECT 1 FROM sdk_guild_members WHERE guild_id = ? AND user_id = ?', (guild_id, leader_id))
        if _cursor.fetchone():
            return False, '你已经加入了一个公会'
        _cursor.execute('INSERT INTO sdk_guilds (guild_id, mod_name, name, description, leader_id) VALUES (?,?,?,?,?)', (guild_id, mod_name, name, description, leader_id))
        _conn.commit()
        sgid = _cursor.lastrowid
        _cursor.execute('INSERT INTO sdk_guild_members (guild_id, sdk_guild_id, user_id, role) VALUES (?,?,?,?)', (guild_id, sgid, leader_id, 'leader'))
        _conn.commit()
        return True, sgid
    except Exception as e:
        return False, str(e)

def guild_join(guild_id, sdk_guild_id, user_id):
    try:
        _cursor.execute('SELECT id FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        if not _cursor.fetchone():
            return False, '公会不存在'
        _cursor.execute('SELECT 1 FROM sdk_guild_members WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        if _cursor.fetchone():
            return False, '你已经加入了一个公会'
        _cursor.execute('INSERT INTO sdk_guild_members (guild_id, sdk_guild_id, user_id, role) VALUES (?,?,?,?)', (guild_id, sdk_guild_id, user_id, 'member'))
        _conn.commit()
        return True, '加入公会成功'
    except Exception as e:
        return False, str(e)

def guild_leave(guild_id, sdk_guild_id, user_id):
    try:
        _cursor.execute('SELECT leader_id FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        row = _cursor.fetchone()
        if row and row[0] == user_id:
            return False, '会长是不能退出公会的'
        _cursor.execute('DELETE FROM sdk_guild_members WHERE sdk_guild_id = ? AND user_id = ?', (sdk_guild_id, user_id))
        _conn.commit()
        return True, '已退出公会'
    except Exception as e:
        return False, str(e)

def guild_list(guild_id=''):
    try:
        query = 'SELECT id, name, level, leader_id FROM sdk_guilds'
        params = []
        if guild_id:
            query += ' WHERE guild_id = ?'
            params.append(guild_id)
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = [{'id': r[0], 'name': r[1], 'level': r[2], 'leader_id': r[3]} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)

# ═══════════════════════════════════════════
# 18. 资料库系统（简化版）
# ═══════════════════════════════════════════

def wiki_create_page(guild_id, mod_name, title, content, author_id, category=''):
    try:
        _cursor.execute('INSERT INTO sdk_wiki_pages (guild_id, mod_name, title, content, author_id, category) VALUES (?,?,?,?,?,?)', (guild_id, mod_name, title, content, author_id, category))
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def wiki_search(guild_id='', keyword=''):
    try:
        query = 'SELECT id, title, author_id, category FROM sdk_wiki_pages WHERE 1=1'
        params = []
        if guild_id:
            query += ' AND guild_id = ?'
            params.append(guild_id)
        if keyword:
            query += ' AND (title LIKE ? OR content LIKE ?)'
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = [{'id': r[0], 'title': r[1], 'author_id': r[2], 'category': r[3]} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)

# ═══════════════════════════════════════════
# 19. 自动化系统（简化版）
# ═══════════════════════════════════════════

def automation_create(guild_id, mod_name, name, trigger_type, trigger_config, action_config, creator_id):
    try:
        _cursor.execute('INSERT INTO sdk_automations (guild_id, mod_name, name, trigger_type, trigger_config, action_config, creator_id) VALUES (?,?,?,?,?,?,?)', (guild_id, mod_name, name, trigger_type, json.dumps(trigger_config), json.dumps(action_config), creator_id))
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)

def automation_list(guild_id=''):
    try:
        query = 'SELECT id, name, trigger_type, enabled FROM sdk_automations WHERE 1=1'
        params = []
        if guild_id:
            query += ' AND guild_id = ?'
            params.append(guild_id)
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = [{'id': r[0], 'name': r[1], 'trigger_type': r[2], 'enabled': bool(r[3])} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)

"""

为 mod_sdk.py 添加卖出系统（市场/拍卖行）的 API 函数

使用方法：将此文件中的函数复制到 mod_sdk.py 中，
放在 load_mod_extensions() 函数之后、SDK_API 字典之前。

"""

# ═══════════════════════════════════════════
# 16. 卖出系统（市场/拍卖行）
# ═══════════════════════════════════════════

def market_sell(user_id, item_id, quantity, price, currency_type='points', currency_id=None, guild_id='', mod_name='', expires_in_days=7):
    """上架物品到市场
    返回 (success, market_id or error_msg)
    """
    try:
        # 检查物品是否存在
        _cursor.execute('SELECT name FROM sdk_items WHERE id = ?', (item_id,))
        item_row = _cursor.fetchone()
        if not item_row:
            return False, f'物品 ID {item_id} 不存在'
        
        # 检查用户是否有足够物品
        _cursor.execute('SELECT quantity FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        inv_row = _cursor.fetchone()
        if not inv_row or inv_row[0] < quantity:
            return False, f'物品数量不足（需要 {quantity}，拥有 {inv_row[0] if inv_row else 0}）'
        
        # 检查物品是否可交易
        _cursor.execute('SELECT transferable FROM sdk_items WHERE id = ?', (item_id,))
        transferable_row = _cursor.fetchone()
        if transferable_row and not transferable_row[0]:
            return False, '该物品不可交易'
        
        # 扣除用户物品
        new_qty = inv_row[0] - quantity
        if new_qty <= 0:
            _cursor.execute('DELETE FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        else:
            _cursor.execute('UPDATE sdk_inventory SET quantity = ? WHERE user_id = ? AND item_id = ?', (new_qty, user_id, item_id))
        
        # 计算过期时间
        expires_at = None
        if expires_in_days > 0:
            from datetime import datetime, timedelta
            expires_at = (datetime.now() + timedelta(days=expires_in_days)).strftime('%Y-%m-%d %H:%M:%S')
        
        # 上架
        _cursor.execute(
            '''INSERT INTO sdk_market 
               (guild_id, mod_name, seller_id, item_id, quantity, price, currency_type, currency_id, expires_at) 
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (guild_id, mod_name, user_id, item_id, quantity, price, currency_type, currency_id, expires_at)
        )
        _conn.commit()
        market_id = _cursor.lastrowid
        return True, market_id
    except Exception as e:
        return False, str(e)

def market_buy(buyer_id, market_id, buy_quantity=1):
    """从市场购买物品
    返回 (success, msg)
    """
    try:
        # 查找市场条目
        _cursor.execute('SELECT * FROM sdk_market WHERE id = ? AND status = "active"', (market_id,))
        market_row = _cursor.fetchone()
        if not market_row:
            return False, '市场条目不存在或已下架'
        
        seller_id = market_row[2]  # seller_id
        item_id = market_row[3]   # item_id
        available_qty = market_row[4]  # quantity
        price = market_row[5]     # price
        currency_type = market_row[6]  # currency_type
        currency_id = market_row[7]    # currency_id
        
        if buyer_id == seller_id:
            return False, '不能购买自己上架的物品'
        
        if buy_quantity > available_qty:
            return False, f'购买数量超过可购买数量（最多 {available_qty}）'
        
        total_price = price * buy_quantity
        
        # 检查买家是否有足够货币
        if currency_type == 'points':
            buyer_balance = get_points(buyer_id)
            if buyer_balance < total_price:
                return False, f'积分不足（需要 {total_price}，拥有 {buyer_balance}）'
            # 扣除买家积分
            add_points(buyer_id, -total_price)
            # 给予卖家积分
            add_points(seller_id, total_price)
        else:
            # 自定义货币
            buyer_balance = currency_get_balance(buyer_id, currency_id)
            if buyer_balance < total_price:
                return False, f'货币不足（需要 {total_price}，拥有 {buyer_balance}）'
            currency_add(buyer_id, currency_id, -total_price)
            currency_add(seller_id, currency_id, total_price)
        
        # 给予买家物品
        item_give(buyer_id, item_id, buy_quantity)
        
        # 更新市场条目
        new_available = available_qty - buy_quantity
        if new_available <= 0:
            _cursor.execute('UPDATE sdk_market SET status = "sold", quantity = 0 WHERE id = ?', (market_id,))
        else:
            _cursor.execute('UPDATE sdk_market SET quantity = ? WHERE id = ?', (new_available, market_id))
        
        # 记录交易
        _cursor.execute(
            '''INSERT INTO sdk_market_transactions 
               (market_id, buyer_id, quantity, total_price, currency_type, currency_id) 
               VALUES (?,?,?,?,?,?)''',
            (market_id, buyer_id, buy_quantity, total_price, currency_type, currency_id)
        )
        _conn.commit()
        
        return True, f'购买成功！花费 {total_price}，获得物品 x{buy_quantity}'
    except Exception as e:
        return False, str(e)

def market_cancel(user_id, market_id):
    """下架物品（只允许卖家下架）
    返回 (success, msg)
    """
    try:
        _cursor.execute('SELECT seller_id, item_id, quantity, status FROM sdk_market WHERE id = ?', (market_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '市场条目不存在'
        if row[0] != user_id:
            return False, '只有卖家才能下架物品'
        if row[3] != 'active':
            return False, f'该物品已 {row[3]}，无法下架'
        
        # 退还物品给卖家
        item_give(user_id, row[1], row[2])
        
        # 更新状态
        _cursor.execute('UPDATE sdk_market SET status = "cancelled" WHERE id = ?', (market_id,))
        _conn.commit()
        return True, '下架成功，物品已退还'
    except Exception as e:
        return False, str(e)

def market_list(guild_id='', mod_name='', item_id=None, page=1, page_size=10):
    """查看市场列表
    返回 (success, list_of_dicts)
    """
    try:
        query = '''SELECT m.id, m.seller_id, m.item_id, i.name, m.quantity, m.price, 
                          m.currency_type, m.currency_id, m.created_at 
                   FROM sdk_market m 
                   JOIN sdk_items i ON m.item_id = i.id 
                   WHERE m.status = "active"'''
        params = []
        if guild_id:
            query += ' AND m.guild_id = ?'
            params.append(guild_id)
        if mod_name:
            query += ' AND m.mod_name = ?'
            params.append(mod_name)
        if item_id:
            query += ' AND m.item_id = ?'
            params.append(item_id)
        query += ' ORDER BY m.created_at DESC LIMIT ? OFFSET ?'
        offset = (page - 1) * page_size
        params.extend([page_size, offset])
        
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'market_id': row[0],
                'seller_id': row[1],
                'item_id': row[2],
                'item_name': row[3],
                'quantity': row[4],
                'price': row[5],
                'currency_type': row[6],
                'currency_id': row[7],
                'created_at': row[8]
            })
        return True, result
    except Exception as e:
        return False, str(e)

def market_my_listings(user_id):
    """查看我的上架物品
    返回 (success, list_of_dicts)
    """
    try:
        _cursor.execute(
            '''SELECT m.id, m.item_id, i.name, m.quantity, m.price, 
                      m.currency_type, m.currency_id, m.status, m.created_at 
               FROM sdk_market m 
               JOIN sdk_items i ON m.item_id = i.id 
               WHERE m.seller_id = ? 
               ORDER BY m.created_at DESC''',
            (user_id,)
        )
        rows = _cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'market_id': row[0],
                'item_id': row[1],
                'item_name': row[2],
                'quantity': row[3],
                'price': row[4],
                'currency_type': row[5],
                'currency_id': row[6],
                'status': row[7],
                'created_at': row[8]
            })
        return True, result
    except Exception as e:
        return False, str(e)

SDK_API = {}

# ══════════════════════════════════════
# 物品使用引擎 (item_use)
# ══════════════════════════════════════

def item_use(user_id, item_id, quantity=1, target_user_id=None):
    """使用物品，根据 properties 中的 effect 字段触发效果。
    支持的效果类型：
      - heal: 恢复点数（食物）
      - buff: 施加增益（加成）
      - chest: 打开宝箱随机获得物品
      - currency: 获得货币
      - points: 获得积分
    返回 (success, result_msg)
    """
    try:
        _cursor.execute('SELECT name, item_type, properties FROM sdk_items WHERE id = ?', (item_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '物品不存在'
        item_name, item_type, props_json = row
        props = json.loads(props_json) if props_json else {}

        # 检查用户是否有该物品
        _cursor.execute('SELECT quantity FROM sdk_inventory WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        inv_row = _cursor.fetchone()
        if not inv_row or inv_row[0] < quantity:
            return False, f'你没有足够的 [{item_name}]'

        effect = props.get('effect', 'none')

        if effect == 'none':
            result_msg = f'使用了 [{item_name}]'

        elif effect == 'heal':
            heal_val = int(props.get('value', 10))
            add_points(user_id, heal_val)
            result_msg = f'[{item_name}] 恢复了 {heal_val} 点状态'

        elif effect == 'currency':
            cid = props.get('currency_id', 1)
            amount = props.get('amount', 0)
            currency_add(user_id, cid, amount)
            result_msg = f'[{item_name}] 获得了货币奖励 {amount}'

        elif effect == 'points':
            amount = props.get('amount', 0)
            add_points(user_id, amount)
            result_msg = f'[{item_name}] 获得了 {amount} 积分'

        elif effect == 'chest':
            loot_table = props.get('loot_table', [])
            min_items = props.get('min_items', 1)
            max_items = props.get('max_items', 3)
            if not loot_table:
                result_msg = f'[{item_name}] 是空的宝箱 😢'
            else:
                import random
                num = random.randint(min_items, max_items)
                got = []
                for _ in range(num):
                    entry = random.choice(loot_table)
                    rid = entry.get('item_id')
                    rqty = entry.get('quantity', 1)
                    if rid:
                        item_give(user_id, rid, rqty)
                        _cursor.execute('SELECT name FROM sdk_items WHERE id = ?', (rid,))
                        rrow = _cursor.fetchone()
                        got.append(rrow[0] if rrow else f'物品{rid}')
                result_msg = f'[{item_name}] 开出了：{", ".join(got)}'

        elif effect == 'buff':
            stat = props.get('stat', 'attack')
            value = props.get('value', 0)
            duration = props.get('duration', 300)
            try:
                _ensure_buff_tables()
                _cursor.execute(
                    'INSERT INTO sdk_active_buffs (user_id, buff_name, stat, value, expires_at) VALUES (?,?,?,?,?)',
                    (user_id, item_name, stat, value,
                     (datetime.now() + timedelta(seconds=duration)).strftime('%Y-%m-%d %H:%M:%S'))
                )
                _conn.commit()
            except Exception:
                pass
            result_msg = f'[{item_name}] 获得 [{stat} +{value}] 持续 {duration}秒'

        elif effect == 'equip':
            attack = props.get('attack', 0)
            defense = props.get('defense', 0)
            try:
                _ensure_buff_tables()
                _cursor.execute(
                    'INSERT OR REPLACE INTO sdk_equipment (user_id, item_id, attack, defense) VALUES (?,?,?,?)',
                    (user_id, item_id, attack, defense)
                )
                _conn.commit()
            except Exception:
                pass
            result_msg = f'[{item_name}] 已装备（攻击+{attack}, 防御+{defense}）'

        else:
            result_msg = f'使用了 [{item_name}]（效果：{effect}）'

        # 消耗物品（可消耗类型）
        if props.get('consumable', True):
            item_take(user_id, item_id, quantity)

        return True, result_msg

    except Exception as e:
        return False, str(e)


def item_list(user_id):
    """查询用户背包，返回列表"""
    try:
        _cursor.execute('''
            SELECT i.id, i.name, i.item_type, inv.quantity, i.properties
            FROM sdk_inventory inv
            JOIN sdk_items i ON inv.item_id = i.id
            WHERE inv.user_id = ?
            ORDER BY i.item_type, i.name
        ''', (user_id,))
        rows = _cursor.fetchall()
        result = []
        for r in rows:
            props = json.loads(r[4]) if r[4] else {}
            result.append({'id': r[0], 'name': r[1], 'type': r[2], 'quantity': r[3], 'effect': props.get('effect', 'none')})
        return True, result
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════
# 增益/装备系统建表
# ══════════════════════════════════════

def _ensure_buff_tables():
    try:
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_active_buffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                buff_name TEXT NOT NULL,
                stat TEXT NOT NULL,
                value REAL DEFAULT 0,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        _cursor.execute('''
            CREATE TABLE IF NOT EXISTS sdk_equipment (
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                attack REAL DEFAULT 0,
                defense REAL DEFAULT 0,
                equipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_id),
                FOREIGN KEY (item_id) REFERENCES sdk_items(id)
            )
        ''')
        _conn.commit()
    except Exception:
        pass


# ══════════════════════════════════════
# 模组商店系统
# ══════════════════════════════════════

def store_create(mod_name, guild_id, name, description=''):
    """为模组创建一个商店"""
    try:
        _cursor.execute(
            'INSERT INTO sdk_shops (guild_id, mod_name, name, description) VALUES (?,?,?,?)',
            (guild_id, mod_name, name, description)
        )
        _conn.commit()
        return True, _cursor.lastrowid
    except Exception as e:
        return False, str(e)


def store_add_item(shop_id, item_id, price, currency_type='points', currency_id=None):
    """往商店添加商品"""
    try:
        _cursor.execute(
            'INSERT INTO sdk_shop_items (shop_id, item_id, price, currency_type, currency_id) VALUES (?,?,?,?,?)',
            (shop_id, item_id, price, currency_type, currency_id)
        )
        _conn.commit()
        return True
    except Exception as e:
        return False, str(e)


def store_buy(buyer_id, shop_item_id, quantity=1):
    """从商店购买商品"""
    try:
        _cursor.execute('SELECT shop_id, item_id, price, currency_type, currency_id FROM sdk_shop_items WHERE id = ?', (shop_item_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '商品不存在'
        shop_id, item_id, price, ctype, cid = row
        total = price * quantity

        if ctype == 'points':
            bal = get_points(buyer_id)
            if bal < total:
                return False, f'积分不足（需要 {total}，拥有 {bal}）'
            add_points(buyer_id, -total)
        else:
            bal = currency_get_balance(buyer_id, cid)
            if bal < total:
                return False, f'货币不足'
            currency_add(buyer_id, cid, -total)

        item_give(buyer_id, item_id, quantity)
        return True, f'购买成功！获得物品 x{quantity}，花费 {total}'
    except Exception as e:
        return False, str(e)


def store_list(shop_id=None, mod_name=None, guild_id=None):
    """查询商店商品列表"""
    try:
        query = '''SELECT si.id, si.shop_id, s.name, i.name, si.price,
                          si.currency_type, si.currency_id, i.item_type
                   FROM sdk_shop_items si
                   JOIN sdk_shops s ON si.shop_id = s.id
                   JOIN sdk_items i ON si.item_id = i.id
                   WHERE 1=1'''
        params = []
        if shop_id:
            query += ' AND si.shop_id = ?'
            params.append(shop_id)
        if mod_name:
            query += ' AND s.mod_name = ?'
            params.append(mod_name)
        if guild_id:
            query += ' AND s.guild_id = ?'
            params.append(guild_id)
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = [{'shop_item_id': r[0], 'shop_name': r[2], 'item_name': r[3],
                   'price': r[4], 'currency_type': r[5], 'item_type': r[7]} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════
# 公会系统扩展函数
# ══════════════════════════════════════

def guild_deposit(guild_id_val, sdk_guild_id, user_id, amount, currency_type='points', currency_id=None):
    """向公会仓库存款"""
    try:
        _cursor.execute('SELECT 1 FROM sdk_guild_members WHERE sdk_guild_id = ? AND user_id = ?', (sdk_guild_id, user_id))
        if not _cursor.fetchone():
            return False, '你不是该公会成员'
        if currency_type == 'points':
            bal = get_points(user_id)
            if bal < amount:
                return False, '积分不足'
            add_points(user_id, -amount)
        else:
            bal = currency_get_balance(user_id, currency_id)
            if bal < amount:
                return False, '货币不足'
            currency_add(user_id, currency_id, -amount)
        _cursor.execute('UPDATE sdk_guilds SET funds = funds + ? WHERE id = ?', (amount, sdk_guild_id))
        _conn.commit()
        return True, f'成功向公会存入 {amount}'
    except Exception as e:
        return False, str(e)


def guild_get_info(sdk_guild_id):
    """获取公会详细信息"""
    try:
        _cursor.execute('SELECT name, description, level, exp, funds, leader_id FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '公会不存在'
        _cursor.execute('SELECT COUNT(*), SUM(contribute_exp) FROM sdk_guild_members WHERE sdk_guild_id = ?', (sdk_guild_id,))
        mrow = _cursor.fetchone()
        return True, {
            'name': row[0], 'description': row[1], 'level': row[2],
            'exp': row[3], 'funds': row[4], 'leader_id': row[5],
            'member_count': mrow[0] or 0, 'total_contrib': mrow[1] or 0
        }
    except Exception as e:
        return False, str(e)


def guild_add_exp(sdk_guild_id, exp_amount):
    """给公会加经验（升级逻辑）"""
    try:
        _cursor.execute('UPDATE sdk_guilds SET exp = exp + ? WHERE id = ?', (exp_amount, sdk_guild_id))
        _cursor.execute('SELECT exp, level FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        row = _cursor.fetchone()
        exp, level = row[0], row[1]
        needed = 100 * level
        while exp >= needed:
            exp -= needed
            level += 1
            needed = 100 * level
        _cursor.execute('UPDATE sdk_guilds SET exp = ?, level = ? WHERE id = ?', (exp, level, sdk_guild_id))
        _conn.commit()
        return True, {'new_level': level, 'exp': exp}
    except Exception as e:
        return False, str(e)


def guild_dissolve(guild_id, sdk_guild_id, user_id):
    """会长解散自己的公会；会长的公会将被彻底删除（含成员、仓库）"""
    try:
        _cursor.execute('SELECT leader_id FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '公会不存在'
        if str(row[0]) != str(user_id):
            return False, '只有会长才能解散公会'
        # 删除成员、仓库、公会本身
        _cursor.execute('DELETE FROM sdk_guild_members WHERE sdk_guild_id = ?', (sdk_guild_id,))
        _cursor.execute('DELETE FROM sdk_guild_storage WHERE sdk_guild_id = ?', (sdk_guild_id,))
        _cursor.execute('DELETE FROM sdk_guilds WHERE id = ?', (sdk_guild_id,))
        _conn.commit()
        return True, '公会已解散'
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════
# 知识库系统扩展函数
# ══════════════════════════════════════

def wiki_edit_page(page_id, new_title=None, new_content=None, new_category=None):
    """编辑知识库页面，自动保存历史版本；author_id 不可被修改"""
    try:
        # 先读取当前版本，保存为历史版本
        _cursor.execute('SELECT title, content, category, author_id FROM sdk_wiki_pages WHERE id = ?', (page_id,))
        row = _cursor.fetchone()
        if not row:
            return False, '页面不存在'
        old_title, old_content, old_category, author_id = row

        # 查询当前最大版本号
        _cursor.execute('SELECT MAX(version_num) FROM sdk_wiki_versions WHERE page_id = ?', (page_id,))
        vrow = _cursor.fetchone()
        next_version = (vrow[0] or 0) + 1

        # 保存历史版本（保存修改前的状态）
        _cursor.execute(
            'INSERT INTO sdk_wiki_versions (page_id, version_num, title, content, category, editor_id) VALUES (?,?,?,?,?,?)',
            (page_id, next_version, old_title, old_content, old_category, author_id)
        )

        # 执行更新（不更新 author_id）
        updates = []
        params = []
        if new_title is not None:
            updates.append('title = ?')
            params.append(new_title)
        if new_content is not None:
            updates.append('content = ?')
            params.append(new_content)
        if new_category is not None:
            updates.append('category = ?')
            params.append(new_category)
        updates.append('updated_at = ?')
        params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        params.append(page_id)
        _cursor.execute('UPDATE sdk_wiki_pages SET ' + ', '.join(updates) + ' WHERE id = ?', params)
        _conn.commit()
        return True, next_version
    except Exception as e:
        return False, str(e)


def wiki_get_page(page_id, version_num=None):
    """获取知识库页面内容；version_num=None 时返回最新版"""
    try:
        if version_num is not None:
            _cursor.execute(
                'SELECT title, content, category, editor_id, edited_at, version_num FROM sdk_wiki_versions WHERE page_id = ? AND version_num = ?',
                (page_id, version_num)
            )
            row = _cursor.fetchone()
            if not row:
                return False, '该版本不存在'
            return True, {
                'title': row[0], 'content': row[1], 'category': row[2],
                'author_id': row[3], 'updated_at': row[4], 'version': row[5],
                'is_history': True
            }
        else:
            _cursor.execute(
                'SELECT title, content, category, author_id, updated_at, created_at FROM sdk_wiki_pages WHERE id = ?',
                (page_id,)
            )
            row = _cursor.fetchone()
            if not row:
                return False, '页面不存在'
            return True, {
                'title': row[0], 'content': row[1], 'category': row[2],
                'author_id': row[3], 'updated_at': row[4], 'created_at': row[5],
                'version': 'latest', 'is_history': False
            }
    except Exception as e:
        return False, str(e)


def wiki_list_versions(page_id):
    """列出页面的所有历史版本（不含最新版）"""
    try:
        _cursor.execute('SELECT version_num, editor_id, edited_at FROM sdk_wiki_versions WHERE page_id = ? ORDER BY version_num DESC', (page_id,))
        rows = _cursor.fetchall()
        result = [{'version': r[0], 'editor_id': r[1], 'edited_at': r[2]} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)


def wiki_delete_page(page_id):
    """删除知识库页面（同时删除版本历史）"""
    try:
        _cursor.execute('DELETE FROM sdk_wiki_versions WHERE page_id = ?', (page_id,))
        _cursor.execute('DELETE FROM sdk_wiki_pages WHERE id = ?', (page_id,))
        _conn.commit()
        return True
    except Exception as e:
        return False, str(e)


def wiki_list_by_category(guild_id=None, category=''):
    """按分类列出知识库页面"""
    try:
        query = 'SELECT id, title, category, author_id FROM sdk_wiki_pages WHERE 1=1'
        params = []
        if guild_id:
            query += ' AND guild_id = ?'
            params.append(guild_id)
        if category:
            query += ' AND category = ?'
            params.append(category)
        query += ' ORDER BY category, title'
        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        result = [{'id': r[0], 'title': r[1], 'category': r[2], 'author_id': r[3]} for r in rows]
        return True, result
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════
# 自动化系统执行引擎
# ══════════════════════════════════════

_automation_task = None


def automation_start_engine(bot_instance):
    """启动自动化引擎后台任务（在 main.py 的 on_ready 中调用）"""
    global _automation_task, _bot
    _bot = bot_instance
    if _automation_task is None or _automation_task.done():
        _automation_task = asyncio.ensure_future(_automation_loop())
        print('[Automation] 引擎已启动')


async def _automation_loop():
    """自动化引擎主循环：每 10 秒检查一次待执行的自动化规则"""
    while True:
        try:
            await _check_and_run_automations()
        except Exception as e:
            print(f'[Automation] 引擎错误: {e}')
        await asyncio.sleep(10)


async def _check_and_run_automations():
    """检查并执行到期的自动化规则"""
    try:
        _cursor.execute(
            'SELECT id, name, trigger_type, trigger_config, action_config FROM sdk_automations WHERE enabled = 1'
        )
        for row in _cursor.fetchall():
            auto_id, name, trigger_type, trigger_config, action_config = row
            tconf = json.loads(trigger_config) if trigger_config else {}
            aconf = json.loads(action_config) if action_config else {}

            should_run = False

            if trigger_type == 'interval':
                interval = tconf.get('interval', 3600)
                _cursor.execute('SELECT last_run_at FROM sdk_automations WHERE id = ?', (auto_id,))
                r = _cursor.fetchone()
                last_run = r[0] if r else None
                if not last_run:
                    should_run = True
                else:
                    try:
                        last_dt = datetime.strptime(last_run, '%Y-%m-%d %H:%M:%S')
                        if (datetime.now() - last_dt).total_seconds() >= interval:
                            should_run = True
                    except Exception:
                        should_run = True

            if should_run:
                await _execute_automation_action(auto_id, aconf)
                _cursor.execute(
                    'UPDATE sdk_automations SET last_run_at = ? WHERE id = ?',
                    (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), auto_id)
                )
                _conn.commit()
    except Exception as e:
        print(f'[Automation] 检查失败: {e}')


async def _execute_automation_action(auto_id, action_config):
    """执行自动化动作"""
    try:
        action_type = action_config.get('type', '')

        if action_type == 'send_message':
            channel_id = action_config.get('channel_id')
            content = action_config.get('content', '')
            if channel_id and _bot:
                channel = _bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(content)

        elif action_type == 'give_item':
            user_id = action_config.get('user_id')
            item_id = action_config.get('item_id')
            quantity = action_config.get('quantity', 1)
            if user_id and item_id:
                item_give(int(user_id), int(item_id), quantity)

        elif action_type == 'add_points':
            user_id = action_config.get('user_id')
            amount = action_config.get('amount', 0)
            if user_id:
                add_points(int(user_id), amount)

    except Exception as e:
        print(f'[Automation] 执行动作失败 (ID={auto_id}): {e}')


def automation_toggle(auto_id, enabled=None):
    """启用/禁用自动化规则"""
    try:
        if enabled is None:
            _cursor.execute('SELECT enabled FROM sdk_automations WHERE id = ?', (auto_id,))
            row = _cursor.fetchone()
            if not row:
                return False, '规则不存在'
            enabled = not bool(row[0])
        _cursor.execute('UPDATE sdk_automations SET enabled = ? WHERE id = ?', (1 if enabled else 0, auto_id))
        _conn.commit()
        return True, '已' + ('启用' if enabled else '禁用')
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════
# 扩展 SDK_API 字典
# ══════════════════════════════════════

SDK_API.update({
    'store_create': store_create,
    'store_add_item': store_add_item,
    'store_buy': store_buy,
    'store_list': store_list,
    'guild_deposit': guild_deposit,
    'guild_get_info': guild_get_info,
    'guild_add_exp': guild_add_exp,
    'wiki_edit_page': wiki_edit_page,
    'wiki_delete_page': wiki_delete_page,
    'wiki_list_by_category': wiki_list_by_category,
    'automation_toggle': automation_toggle,
    'automation_start_engine': automation_start_engine,
})

# ══════════════════════════════════════
# SDK_API 完整导出字典（所有函数已定义）
# ══════════════════════════════════════

SDK_API = {
    'currency_create': currency_create,
    'currency_get_balance': currency_get_balance,
    'currency_add': currency_add,
    'currency_transfer': currency_transfer,
    'item_create': item_create,
    'item_give': item_give,
    'item_take': item_take,
    'item_transfer': item_transfer,
    'item_use': item_use,
    'item_list': item_list,
    'storage_bag_create': storage_bag_create,
    'storage_bag_put': storage_bag_put,
    'storage_bag_take': storage_bag_take,
    'custom_game_create': custom_game_create,
    'custom_game_finish': custom_game_finish,
    'red_packet_create': red_packet_create,
    'red_packet_claim': red_packet_claim,
    'currency_mass_send': currency_mass_send,
    'custom_channel_add': custom_channel_add,
    'custom_role_add': custom_role_add,
    'note_create': note_create,
    'note_list': note_list,
    'calc_save': calc_save,
    'todo_add': todo_add,
    'todo_list': todo_list,
    'todo_complete': todo_complete,
    'mod_dep_add': mod_dep_add,

    # 16. 卖出系统
    'market_sell': market_sell,
    'market_buy': market_buy,
    'market_cancel': market_cancel,
    'market_list': market_list,
    'market_my_listings': market_my_listings,

    # 17. 公会系统
    'guild_create': guild_create,
    'guild_join': guild_join,
    'guild_leave': guild_leave,
    'guild_list': guild_list,
    'guild_deposit': guild_deposit,
    'guild_get_info': guild_get_info,
    'guild_add_exp': guild_add_exp,
    'guild_dissolve': guild_dissolve,

    # 18. 商店系统
    'store_create': store_create,
    'store_add_item': store_add_item,
    'store_buy': store_buy,
    'store_list': store_list,

    # 19. 资料库系统
    'wiki_create_page': wiki_create_page,
    'wiki_search': wiki_search,
    'wiki_edit_page': wiki_edit_page,
    'wiki_delete_page': wiki_delete_page,
    'wiki_get_page': wiki_get_page,
    'wiki_list_versions': wiki_list_versions,
    'wiki_list_by_category': wiki_list_by_category,

    # 20. 自动化系统
    'automation_create': automation_create,
    'automation_list': automation_list,
    'automation_toggle': automation_toggle,
    'automation_start_engine': automation_start_engine,

    # 工具函数
    'currency_exchange': currency_exchange,
    'mod_dep_check': mod_dep_check,
    'load_mod_extensions': load_mod_extensions,
    'get_points': get_points,
    'add_points': add_points,
}

