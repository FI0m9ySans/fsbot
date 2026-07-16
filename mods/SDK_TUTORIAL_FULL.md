# FSBot 扩展模组 SDK 完整教程

> 本文档适用于**模组创作者**，介绍如何使用 `.fsbods` 格式和 `mod_sdk` API 来扩展 FSBot。

---

## 目录

1. [扩展系统简介](#1-扩展系统简介)
2. [环境准备](#2-环境准备)
3. [`.fsbods` 扩展字段参考](#3-fsbods-扩展字段参考)
4. [功能详解](#4-功能详解)
5. [SDK API 速查表](#5-sdk-api-速查表)
6. [示例模组解读](#6-示例模组解读)
7. [高级：编写动态命令（Python）](#7-高级编写动态命令python)
8. [调试技巧](#8-调试技巧)

---

## 1. 扩展系统简介

FSBot 的模组系统在原有的 `commands`/`auto_messages`/`replies` 基础上，新增了 **扩展字段**，让模组创作者可以通过 JSON 配置来定义：

| 功能 | 字段名 | 说明 |
|------|--------|------|
| 1. 自定义货币 | `currencies` | 创建新虚拟货币及获取方式 |
| 2. 自定义游戏 | `games` | 消耗/奖励自定义货币的自定义游戏 |
| 3. 红包系统 | `red_packets` | 创建可领取的红包 |
| 4. 群发货币 | — | 通过 SDK API 调用 |
| 5. 自定义频道ID | `custom_channels` | 存储模组使用的频道ID |
| 6. 自定义身份组ID | `custom_roles` | 存储模组使用的身份组ID |
| 7. 自定义商品/商店 | `shops` | 创建商店和商品 |
| 8. 自定义宝箱 | `items` (type:box) | 定义宝箱及开启方式 |
| 9. 储物袋 | SDK API | 通过 API 创建和管理 |
| 10. 记事本 | SDK API | 通过 API 增删改查 |
| 11. 计算器 | SDK API | 通过 API 计算 |
| 12. 待办事项 | SDK API | 通过 API 管理 |
| 13/14. 物品转交控制 | `items.transferable` | 定义物品是否可转交 |
| 15. 父子模组依赖 | `dependencies` | 声明模组依赖关系 |

---

## 2. 环境准备

1. 确保 `mod_sdk.py` 和 `main.py` 在同一目录（`D:/FSBot/`）
2. 确保 `mods/` 目录存在
3. 重启 bot，看到 `[ModSDK] 扩展 SDK 初始化完成` 即表示成功

---

## 3. `.fsbods` 扩展字段参考

### 3.1 `currencies` — 自定义货币

```json
"currencies": [
  {
    "name": "金币",
    "symbol": "🟡",
    "description": "冒险者通用货币",
    "earn_methods": [
      {"type": "command", "command": "/daily", "amount": 50},
      {"type": "message", "amount": 1, "chance": 0.05}
    ]
  }
]
```

**`earn_methods` 类型：**
- `command`：当某命令被执行时发放（需在命令 response 中调用 SDK API）
- `message`：每发送一条消息有机会获得
- `exchange`：用其他货币兑换

> ⚠️ 注意：`earn_methods` 目前仅作记录用途，实际发放需要在命令/消息处理逻辑中调用 SDK API。

---

### 3.2 `items` — 物品定义

```json
"items": [
  {
    "name": "木剑",
    "type": "weapon",
    "description": "新手武器，攻击力+5",
    "properties": {"damage": 5, "durability": 100},
    "transferable": true
  },
  {
    "name": "神秘宝箱",
    "type": "box",
    "description": "打开后随机获得一件物品",
    "properties": {
      "contents": [
        {"item": "木剑", "weight": 50},
        {"item": "面包", "weight": 30}
      ]
    },
    "transferable": true
  }
]
```

**`type` 可选值：** `weapon` / `food` / `buff` / `tool` / `box` / `container` / `custom`

**`transferable`：** `true` = 可转交，`false` = 绑定（功能13/14）

---

### 3.3 `shops` — 商店

```json
"shops": [
  {
    "name": "冒险者商店",
    "description": "购买冒险所需物品",
    "items": [
      {"item": "木剑", "price": 100, "currency": "points"},
      {"item": "神秘宝箱", "price": 5, "currency": "金币"}
    ]
  }
]
```

**`currency` 值：**
- `"points"` = 使用默认积分
- `"金币"` = 使用自定义货币（名称需与 `currencies` 中定义的一致）

---

### 3.4 `red_packets` — 红包模板

```json
"red_packets": [
  {
    "name": "新人红包",
    "description": "新人加入频道时自动发放",
    "amount": 100,
    "currency": "points",
    "quantity": 10
  }
]
```

> 模板需在运行时通过 SDK API 创建实例。

---

### 3.5 `custom_channels` / `custom_roles`

```json
"custom_channels": [
  {"channel_id": "1516860607217926316", "description": "Bump提醒频道"}
],
"custom_roles": [
  {"role_id": "1517070447173435473", "description": "管理员身份组"}
]
```

---

### 3.6 `dependencies` — 父子模组依赖（功能15）

```json
"dependencies": [
  {"name": "example_mod", "type": "requires"},
  {"name": "other_mod", "type": "optional"}
]
```

- `requires`：依赖的模组必须已加载，否则拒绝加载
- `optional`：依赖的模组若已加载，则启用额外功能

---

## 4. 功能详解

### 功能1：自定义货币

**创建货币：** 在 `.fsbods` 中定义 `currencies` 字段（见 §3.1）

**查询余额：** 需在 `commands` 中定义查询命令，并在 `response` 中调用 SDK API（见 §7）

**发放货币：** 通过 SDK API `currency_add(user_id, currency_id, amount)`

---

### 功能2：自定义游戏

目前需要在 Python 代码中创建游戏逻辑。

**步骤：**
1. 在 `.fsbods` 中定义游戏元数据（可选）
2. 编写 Python 函数处理游戏逻辑
3. 使用 `custom_game_create` 和 `custom_game_finish` SDK API

详见 §7 高级部分。

---

### 功能3/4：红包与群发

**创建红包：**
```python
# 在 Python 代码中
ok, rp_id = red_packet_create(
    guild_id, mod_name, creator_id,
    name="幸运红包", total_amount=500,
    currency_type="points", quantity=5
)
```

**领取红包：**
```python
ok, amount, msg = red_packet_claim(rp_id, user_id)
```

**群发货币：**
```python
ok, msg = currency_mass_send(
    guild_id, mod_name,
    currency_type="points", currency_id=None,
    amount_per_user=10, target_filter="all"
)
```

---

### 功能7：自定义商品

见 §3.3 `shops` 字段说明。

**购买流程（需在命令中实现）：**
1. 调用 `item_give(user_id, item_id)` 发放物品
2. 调用 `add_points(user_id, -price)` 或 `currency_add(user_id, currency_id, -price)` 扣除货币

---

### 功能8：自定义宝箱

定义 `type: "box"` 的物品（见 §3.2），在 `properties.contents` 中设置随机池。

**开启宝箱（需在命令中实现）：**
1. 读取宝箱的 `contents` 配置
2. 按权重随机选择一件物品
3. 调用 `item_give(user_id, selected_item_id)` 发放

---

### 功能9：储物袋

```python
# 创建储物袋
ok, bag_id = storage_bag_create(user_id, mod_name, name="我的储物袋", capacity=20)

# 放入物品
ok, msg = storage_bag_put(bag_id, item_id, quantity=1)

# 取出物品
ok, result = storage_bag_take(bag_id, index=0, quantity=1)
```

---

### 功能10/11/12：记事本/计算器/待办

```python
# 记事本
note_create(user_id, mod_name, title="购物清单", content="...")
notes = note_list(user_id, mod_name)

# 计算器
calc_save(user_id, "1+2*3", "7")

# 待办
todo_add(user_id, mod_name, task="完成模组")
todos = todo_list(user_id)
todo_complete(todo_id)
```

---

### 功能13/14：物品转交控制

在 `items` 定义中设置 `"transferable": true/false`

**转交物品：**
```python
ok, msg = item_transfer(from_user_id, to_user_id, item_id, quantity=1)
```

---

## 5. SDK API 速查表

| 函数名 | 功能 | 关键参数 |
|--------|------|----------|
| `currency_create()` | 创建货币 | guild_id, mod_name, name, symbol |
| `currency_get_balance()` | 查询余额 | user_id, currency_id |
| `currency_add()` | 增减货币 | user_id, currency_id, amount |
| `currency_transfer()` | 转账 | from_user, to_user, currency_id, amount |
| `item_create()` | 创建物品定义 | guild_id, mod_name, name, type |
| `item_give()` | 发放物品 | user_id, item_id, quantity |
| `item_take()` | 收回物品 | user_id, item_id, quantity |
| `item_transfer()` | 转交物品 | from_user, to_user, item_id |
| `storage_bag_create()` | 创建储物袋 | user_id, mod_name, name |
| `storage_bag_put()` | 存入物品 | bag_id, item_id, quantity |
| `storage_bag_take()` | 取出物品 | bag_id, index, quantity |
| `red_packet_create()` | 创建红包 | guild_id, creator_id, name, amount |
| `red_packet_claim()` | 领取红包 | rp_id, user_id |
| `currency_mass_send()` | 群发货币 | guild_id, currency_type, amount |
| `note_create()` | 创建笔记 | user_id, title, content |
| `note_list()` | 列出笔记 | user_id |
| `todo_add()` | 添加待办 | user_id, task |
| `todo_list()` | 列出待办 | user_id |
| `todo_complete()` | 完成待办 | todo_id |
| `custom_game_create()` | 创建自定义游戏 | guild_id, player1, player2 |
| `custom_game_finish()` | 结束游戏发奖 | game_id, winner_id |
| `mod_dep_add()` | 添加依赖 | mod_name, depends_on, type |
| `mod_dep_check()` | 检查依赖 | mod_name |

> 所有函数均在 `mod_sdk.py` 中定义，通过 `mod_sdk.SDK_API` 字典访问。

---

## 6. 示例模组解读

文件：`mods/example_mod_full.fsbods`

该示例展示了：
- 如何定义自定义货币"金币"和"钻石"
- 如何定义物品（木剑、面包、神秘宝箱、钥匙、绑定戒指）
- 如何定义商店"冒险者商店"
- 如何定义红包模板
- 如何定义自定义频道和身份组ID
- 如何声明依赖关系
- 如何定义静态命令和关键词回复

**加载示例模组：**
1. 将 `example_mod_full.fsbods` 放入 `mods/` 目录
2. 重启 bot，或执行 `/uploadmods` 上传
3. 看到 `✅ 模组 "example_full" 加载成功` 即表示成功

---

## 7. 高级：编写动态命令（Python）

目前 `.fsbods` 的 `commands` 字段仅支持**静态响应**（`response` 固定文本）。

若需**动态命令**（如查询实时余额、购买物品等），需编写 Python 代码：

### 步骤1：创建模组 Python 文件

在 `mods/` 目录下创建 `my_mod.py`：

```python
import mod_sdk as sdk

# 查询余额命令
async def cmd_balance(interaction: discord.Interaction):
    user_id = interaction.user.id
    # 查询积分
    points = sdk.get_points(user_id)
    # 查询自定义货币（需先获取 currency_id）
    # ...
    await interaction.response.send_message(f"⭐ 积分：{points}")

# 注册命令（在 bot 启动时调用）
def register_commands(bot):
    @bot.tree.command(name="my_balance")
    async def my_balance(interaction: discord.Interaction):
        await cmd_balance(interaction)
```

### 步骤2：在 `.fsbods` 中声明 Python 文件

目前系统暂不支持自动加载 Python 文件。若需此功能，请在 `main.py` 中手动添加 import。

> 💡 **未来改进方向：** 支持在 `.fsbods` 中指定 `handler` 字段，指向 Python 函数。

---

## 8. 调试技巧

1. **查看加载日志：** bot 启动时会在控制台输出 `[ModSDK]` 开头的日志
2. **检查数据库：** 使用 SQLite 工具打开 `users.db`，查看 `sd_` 开头的表
3. **测试命令：** 加载模组后，在 Discord 中执行 `/` 查看新注册的命令
4. **查看错误：** 若命令注册失败，错误会包含在加载成功的返回消息中

---

## 附录：完整 `.fsbods` 格式模板

```json
{
  "name": "my_mod",
  "version": "1.0",
  "description": "我的模组",
  "commands": [{"name": "...", "description": "...", "response": {...}}],
  "auto_messages": [{"channel_id": 123, "interval_hours": 24, "message": {...}}],
  "replies": [{"trigger": "...", "match": "contains", "response": "..."}],
  "currencies": [{"name": "...", "symbol": "...", "earn_methods": []}],
  "items": [{"name": "...", "type": "weapon", "properties": {}, "transferable": true}],
  "shops": [{"name": "...", "items": [{"item": "...", "price": 100}]}],
  "red_packets": [{"name": "...", "amount": 100, "quantity": 5}],
  "custom_channels": [{"channel_id": "123", "description": "..."}],
  "custom_roles": [{"role_id": "123", "description": "..."}],
  "dependencies": [{"name": "other_mod", "type": "requires"}]
}
```

---

## 7. `action` 字段：创建动态命令（无需编写 Python 代码）

> ⚠️ **需要 main.py 支持**：此功能需要 `main.py` 中的 `load_mod` 函数已更新以支持 `action` 字段（本教程编写时已实现）。

### 7.1 基本格式

在 `commands` 数组中的某个命令里，添加 `action` 字段：

```json
{
  "name": "check_gold",
  "description": "查看我的金币余额",
  "action": {
    "function": "currency_get_balance",
    "args": [{"var": "user_id"}, 1],
    "response": "你的金币余额：{result}"
  }
}
```

**字段说明：**
- `function`（或 `sdk_func`）：要调用的 SDK 函数名（必须在 `mod_sdk.SDK_API` 中）
- `args`（或 `sdk_args`）：参数列表
  - 字面量（数字、字符串）→ 直接传递
  - `{"var": "user_id"}` → 替换为 `interaction.user.id`
  - `{"var": "guild_id"}` → 替换为 `interaction.guild.id`
  - `{"var": "channel_id"}` → 替换为 `interaction.channel.id`
  - `null` → 替换为 `interaction.user.id`（默认第一个参数为用户ID）
- `response`：响应模板
  - 字符串：`{result}` 会被函数返回值替换
  - 字典：多语言模板 `{"zh": "...", "en": "..."}`

### 7.2 示例：查询余额

```json
{
  "name": "my_balance",
  "description": "查询我的金币余额",
  "action": {
    "function": "currency_get_balance",
    "args": [{"var": "user_id"}, 1],
    "response": {
      "zh": "你的金币余额：{result} 🟡",
      "en": "Your gold balance: {result} 🟡"
    }
  }
}
```

**工作流程：**
1. 用户执行 `/my_balance`
2. Bot 调用 `currency_get_balance(user_id, 1)`（1 是货币 ID）
3. 返回结果（例如 500）
4. 发送消息：`你的金币余额：500 🟡`

### 7.3 示例：给予物品

```json
{
  "name": "get_starter_pack",
  "description": "领取新手礼包（内含木剑）",
  "action": {
    "function": "item_give",
    "args": [{"var": "user_id"}, 1, 1],
    "response": {
      "zh": "✅ 已领取新手礼包！获得：木剑 x1",
      "en": "✅ Starter pack claimed! You got: Wooden Sword x1"
    }
  }
}
```

**注意：** `item_id` (这里为 1）需要是 `items` 表中已有的物品 ID。您可以在 `items` 字段中定义物品，然后加载后查看数据库获取 ID。

### 7.4 支持的函数列表

`action.function` 可接受以下函数名（来自 `mod_sdk.SDK_API`）：

| 函数名 | 说明 | 参数示例 |
|---------|------|---------|
| `currency_get_balance` | 查询货币余额 | `(user_id, currency_id)` |
| `currency_add` | 增加货币 | `(user_id, currency_id, amount)` |
| `item_give` | 给予物品 | `(user_id, item_id, quantity)` |
| `item_take` | 扣除物品 | `(user_id, item_id, quantity)` |
| `note_create` | 创建记事 | `(user_id, mod_name, title, content)` |
| `todo_add` | 添加待办 | `(user_id, mod_name, task)` |
| `red_packet_create` | 创建红包 | `(guild_id, mod_name, creator_id, name, amount, ...)` |
| ... | 参见 `mod_sdk.SDK_API` | ... |

### 7.5 高级：复杂响应

如果 `response` 是字符串，可以使用多个 `{result}` 占位符：

```json
{
  "name": "my_info",
  "description": "查看我的信息",
  "action": {
    "function": "get_user_info",
    "args": [{"var": "user_id"}],
    "response": "用户ID: {result[id]}\n积分: {result[points]}\n等级: {result[level]}"
  }
}
```

（注：此功能需要 `get_user_info` 函数返回字典，并且响应模板支持字典键访问。当前版本可能不支持，请测试后使用。）

---

## 8. 高级：编写动态命令（Python）

> 如果 `action` 字段无法满足需求，您可以：
> 1. Fork 本仓库
> 2. 修改 `main.py` 或 `mod_sdk.py`
> 3. 提交 Pull Request

（本节预留，待后续版本完善）

---

## 9. 调试技巧

1. **查看 bot 控制台输出**：加载模组时会有日志输出（`[ModSDK] ...`）
2. **检查数据库**：使用 SQLite 浏览器打开 `users.db`，查看 `sdk_*` 表
3. **测试命令**：使用 `/sdk_balance`、`/sdk_items` 等通用命令验证数据
4. **查看错误**：如果命令注册失败，错误会记录在 bot 控制台，也会在 `/uploadmods` 的响应中显示

---

*教程版本：1.1 | 更新日期：2026-06-22*
