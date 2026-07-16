# ==========================================
# 通用 SDK 斜杠命令（让用户直接使用扩展功能）
# ==========================================

if _mod_sdk:
    @bot.tree.command(name='sdk_balance', description='💰 查询自定义货币余额 / Check custom currency balance')
    async def sdk_balance_slash(interaction: discord.Interaction):
        """查询当前用户的所有自定义货币余额"""
        user_id = interaction.user.id
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
        
        try:
            # 查询所有货币
            _mod_sdk._cursor.execute('SELECT id, name, symbol FROM sdk_currencies')
            currencies = _mod_sdk._cursor.fetchall()
            
            if not currencies:
                if lang == 'zh':
                    await interaction.response.send_message('❌ 当前没有可用的自定义货币。', ephemeral=True)
                elif lang == 'ja':
                    await interaction.response.send_message('❌ カスタム通貨はありません。', ephemeral=True)
                elif lang == 'fr':
                    await interaction.response.send_message('❌ Aucune monnaie personnalisée disponible.', ephemeral=True)
                else:
                    await interaction.response.send_message('❌ No custom currencies available.', ephemeral=True)
                return
            
            # 构建余额信息
            lines = []
            for cid, cname, csymbol in currencies:
                bal = _mod_sdk.currency_get_balance(user_id, cid)
                symbol_str = csymbol + ' ' if csymbol else ''
                lines.append(f'{symbol_str}**{cname}**: {bal}')
            
            if lang == 'zh':
                embed = discord.Embed(title='💰 自定义货币余额', description='\n'.join(lines) or '暂无余额', color=discord.Color.gold())
            elif lang == 'ja':
                embed = discord.Embed(title='💴 カスタム通貨残高', description='\n'.join(lines) or '残高なし', color=discord.Color.gold())
            elif lang == 'fr':
                embed = discord.Embed(title='💶 Solde monnaies personnalisées', description='\n'.join(lines) or 'Aucun solde', color=discord.Color.gold())
            else:
                embed = discord.Embed(title='💰 Custom Currency Balance', description='\n'.join(lines) or 'No balance', color=discord.Color.gold())
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 错误：{e}', ephemeral=True)

    @bot.tree.command(name='sdk_items', description='🎒 查看背包 / View inventory')
    async def sdk_items_slash(interaction: discord.Interaction):
        """查看当前用户的物品背包"""
        user_id = interaction.user.id
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
        
        try:
            _mod_sdk._cursor.execute('''
                SELECT i.name, i.item_type, inv.quantity, i.id
                FROM sdk_inventory inv
                JOIN sdk_items i ON inv.item_id = i.id
                WHERE inv.user_id = ?
            ''', (user_id,))
            items = _mod_sdk._cursor.fetchall()
            
            if not items:
                if lang == 'zh':
                    msg = '❌ 背包为空。'
                elif lang == 'ja':
                    msg = '❌ インベントリは空です。'
                elif lang == 'fr':
                    msg = '❌ L\'inventaire est vide.'
                else:
                    msg = '❌ Inventory is empty.'
                await interaction.response.send_message(msg, ephemeral=True)
                return
            
            lines = []
            for iname, itype, qty, iid in items:
                lines.append(f'• **{iname}** ({itype}) x{qty} [ID:{iid}]')
            
            if lang == 'zh':
                embed = discord.Embed(title='🎒 背包', description='\n'.join(lines), color=discord.Color.blue())
            elif lang == 'ja':
                embed = discord.Embed(title='🎒 インベントリ', description='\n'.join(lines), color=discord.Color.blue())
            elif lang == 'fr':
                embed = discord.Embed(title='🎒 Inventaire', description='\n'.join(lines), color=discord.Color.blue())
            else:
                embed = discord.Embed(title='🎒 Inventory', description='\n'.join(lines), color=discord.Color.blue())
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 错误：{e}', ephemeral=True)

    @bot.tree.command(name='sdk_shops', description='🛒 查看所有商店 / View all shops')
    async def sdk_shops_slash(interaction: discord.Interaction):
        """列出所有商店"""
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
        
        try:
            _mod_sdk._cursor.execute('SELECT id, name, description FROM sdk_shops')
            shops = _mod_sdk._cursor.fetchall()
            
            if not shops:
                if lang == 'zh':
                    msg = '❌ 当前没有商店。'
                elif lang == 'ja':
                    msg = '❌ ショップはありません。'
                elif lang == 'fr':
                    msg = '❌ Aucune boutique disponible.'
                else:
                    msg = '❌ No shops available.'
                await interaction.response.send_message(msg, ephemeral=True)
                return
            
            lines = []
            for sid, sname, sdesc in shops:
                desc_str = f' - {sdesc}' if sdesc else ''
                lines.append(f'• **{sname}** (ID:{sid}){desc_str}')
            
            if lang == 'zh':
                embed = discord.Embed(title='🛒 所有商店', description='\n'.join(lines), color=discord.Color.green())
            elif lang == 'ja':
                embed = discord.Embed(title='🛒 すべてのショップ', description='\n'.join(lines), color=discord.Color.green())
            elif lang == 'fr':
                embed = discord.Embed(title='🛒 Toutes les boutiques', description='\n'.join(lines), color=discord.Color.green())
            else:
                embed = discord.Embed(title='🛒 All Shops', description='\n'.join(lines), color=discord.Color.green())
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 错误：{e}', ephemeral=True)

    @bot.tree.command(name='sdk_notes', description='📝 查看记事本 / View notes')
    async def sdk_notes_slash(interaction: discord.Interaction):
        """查看当前用户的记事本列表"""
        user_id = interaction.user.id
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
        
        try:
            notes = _mod_sdk.note_list(user_id)
            
            if not notes:
                if lang == 'zh':
                    msg = '❌ 记事本为空。'
                elif lang == 'ja':
                    msg = '❌ ノートは空です。'
                elif lang == 'fr':
                    msg = '❌ Aucune note.'
                else:
                    msg = '❌ No notes.'
                await interaction.response.send_message(msg, ephemeral=True)
                return
            
            lines = []
            for nid, ntitle, ncreated in notes:
                lines.append(f'• [{nid}] **{ntitle}** — {ncreated}')
            
            if lang == 'zh':
                embed = discord.Embed(title='📝 记事本', description='\n'.join(lines), color=discord.Color.orange())
            elif lang == 'ja':
                embed = discord.Embed(title='📝 ノート', description='\n'.join(lines), color=discord.Color.orange())
            elif lang == 'fr':
                embed = discord.Embed(title='📝 Notes', description='\n'.join(lines), color=discord.Color.orange())
            else:
                embed = discord.Embed(title='📝 Notes', description='\n'.join(lines), color=discord.Color.orange())
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 错误：{e}', ephemeral=True)

    @bot.tree.command(name='sdk_todos', description='✅ 查看待办事项 / View todos')
    async def sdk_todos_slash(interaction: discord.Interaction):
        """查看当前用户的待办事项"""
        user_id = interaction.user.id
        locale = str(interaction.locale)
        lang = 'zh' if locale.startswith('zh') else ('ja' if locale.startswith('ja') else ('fr' if locale.startswith('fr') else 'en'))
        
        try:
            todos = _mod_sdk.todo_list(user_id)
            
            if not todos:
                if lang == 'zh':
                    msg = '❌ 待办事项为空。'
                elif lang == 'ja':
                    msg = '❌ やることリストは空です。'
                elif lang == 'fr':
                    msg = '❌ Aucune tâche.'
                else:
                    msg = '❌ No todos.'
                await interaction.response.send_message(msg, ephemeral=True)
                return
            
            lines = []
            for tid, ttask, tcompleted in todos:
                checkbox = '✅' if tcompleted else '⬜'
                lines.append(f'{checkbox} [{tid}] {ttask}')
            
            if lang == 'zh':
                embed = discord.Embed(title='✅ 待办事项', description='\n'.join(lines), color=discord.Color.purple())
            elif lang == 'ja':
                embed = discord.Embed(title='✅ やることリスト', description='\n'.join(lines), color=discord.Color.purple())
            elif lang == 'fr':
                embed = discord.Embed(title='✅ Tâches', description='\n'.join(lines), color=discord.Color.purple())
            else:
                embed = discord.Embed(title='✅ Todos', description='\n'.join(lines), color=discord.Color.purple())
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ 错误：{e}', ephemeral=True)

    print("[SDK] 通用斜杠命令注册完成：/sdk_balance, /sdk_items, /sdk_shops, /sdk_notes, /sdk_todos")
else:
    print("[SDK] 通用斜杠命令未注册（mod_sdk 不可用）")
