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
