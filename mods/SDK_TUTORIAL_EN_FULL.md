# FSBot Mod SDK Tutorial (English Version)

> **Complete guide to creating mods with 22+ extended features**  
> **For mod creators who want to add custom currencies, items, shops, guilds, automation, and more to FSBot.**

---

## Table of Contents

1. [Quick Start](#1-quick-start)  
2. [`.fsbods` Format Overview](#2-fsbods-format-overview)  
3. [Extended Features Reference](#3-extended-features-reference)  
   - 3.1 [Custom Currencies](#31-custom-currencies)  
   - 3.2 [Custom Items](#32-custom-items)  
   - 3.3 [Custom Shops](#33-custom-shops)  
   - 3.4 [Red Packet System](#34-red-packet-system)  
   - 3.5 [Storage Bags](#35-storage-bags)  
   - 3.6 [Notepad](#36-notepad)  
   - 3.7 [Todo List](#37-todo-list)  
   - 3.8 [Calculator](#38-calculator)  
   - 3.9 [Market System](#39-market-system)  
   - 3.10 [Guild System](#310-guild-system)  
   - 3.11 [Wiki System](#311-wiki-system)  
   - 3.12 [Automation System](#312-automation-system)  
4. [The `action` Field: Dynamic Commands](#4-the-action-field-dynamic-commands)  
5. [Debugging Tips](#5-debugging-tips)  

---

## 1. Quick Start

### Step 1: Create a mod file

Create a new file `my_mod.fsbods` in the `mods/` folder:

```json
{
  "name": "my_mod",
  "description": "My first mod with custom currency and items",
  "version": "1.0",
  "author": "YourName",
  "commands": [
    {
      "name": "hello",
      "description": "Say hello",
      "response": "Hello from my mod!"
    }
  ],
  "currencies": [
    {
      "name": "Gold Coin",
      "symbol": "🟡",
      "description": "Currency for my mod"
    }
  ],
  "items": [
    {
      "name": "Health Potion",
      "type": "consumable",
      "description": "Restores 50 HP",
      "transferable": true
    }
  ]
}
```

### Step 2: Upload the mod

In Discord, run:
```
/uploadmods
```
Then attach your `my_mod.fsbods` file.

### Step 3: Test

The bot will automatically load your mod and create the currency + items.

---

## 2. `.fsbods` Format Overview

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Mod name (unique identifier) |
| `description` | string | ❌ | Mod description |
| `version` | string | ❌ | Version number |
| `author` | string | ❌ | Author name |
| `commands` | array | ❌ | Custom slash commands |
| `auto_messages` | array | ❌ | Auto-reply messages |
| `replies` | array | ❌ | Keyword-triggered replies |
| `currencies` | array | ❌ | Custom currencies |
| `items` | array | ❌ | Custom items |
| `shops` | array | ❌ | Custom shops |
| `red_packets` | array | ❌ | Red packet templates |
| `custom_channels` | array | ❌ | Custom channel IDs |
| `custom_roles` | array | ❌ | Custom role IDs |
| `dependencies` | array | ❌ | Mod dependencies |
| `market_sell` | array | ❌ | Market sell templates |

---

## 3. Extended Features Reference

### 3.1 Custom Currencies

**What it does:** Creates a new currency (like "Gold Coins", "Diamonds", etc.)

**`.fsbods` format:**
```json
{
  "currencies": [
    {
      "name": "Gold Coin",
      "symbol": "🟡",
      "description": "Currency for trading",
      "earn_methods": [
        {"type": "command", "command": "/daily", "amount": 100},
        {"type": "message", "amount": 1, "chance": 0.1}
      ]
    }
  ]
}
```

**SDK API functions:**
- `currency_create(guild_id, mod_name, name, symbol, description)`
- `currency_get_balance(user_id, currency_id)`
- `currency_add(user_id, currency_id, amount)`
- `currency_transfer(from_user, to_user, currency_id, amount)`

---

### 3.2 Custom Items

**What it does:** Creates custom items (weapons, potions, materials, etc.)

**`.fsbods` format:**
```json
{
  "items": [
    {
      "name": "Iron Sword",
      "type": "weapon",
      "description": "A basic iron sword",
      "properties": {"attack": 10, "durability": 100},
      "transferable": true
    },
    {
      "name": "Health Potion",
      "type": "consumable",
      "description": "Restores 50 HP",
      "properties": {"heal": 50},
      "transferable": true
    }
  ]
}
```

**Item types:** `weapon`, `armor`, `consumable`, `material`, `quest`, `box`, `food`, `booster`

**SDK API functions:**
- `item_create(guild_id, mod_name, name, item_type, description, properties)`
- `item_give(user_id, item_id, quantity)`
- `item_take(user_id, item_id, quantity)`
- `item_transfer(from_user, to_user, item_id, quantity)`

---

### 3.3 Custom Shops

**What it does:** Creates shops where players can buy items

**`.fsbods` format:**
```json
{
  "shops": [
    {
      "name": "Weapon Shop",
      "description": "Buy weapons here",
      "items": [
        {"item_id": 1, "price": 100, "currency_type": "points"},
        {"item_id": 2, "price": 50, "currency_type": "points"}
      ]
    }
  ]
}
```

**SDK API functions:**
- `shop_create(guild_id, mod_name, name, description)`
- `shop_add_item(shop_id, item_id, price, currency_type)`

---

### 3.4 Red Packet System

**What it does:** Creates red packets (lucky draw-style rewards)

**`.fsbods` format:**
```json
{
  "red_packets": [
    {
      "name": "Daily Gift",
      "description": "Daily red packet",
      "total_amount": 100,
      "quantity": 10,
      "currency_type": "points"
    }
  ]
}
```

**SDK API functions:**
- `red_packet_create(guild_id, mod_name, creator_id, name, total_amount, quantity)`
- `red_packet_claim(user_id, rp_id)`

---

### 3.5 Storage Bags

**What it does:** Creates personal storage for extra inventory space

**SDK API functions:**
- `storage_bag_create(user_id, mod_name, name, capacity)`
- `storage_bag_put(user_id, bag_id, item_id, quantity)`
- `storage_bag_take(user_id, bag_id, item_id, quantity)`

---

### 3.6 Notepad

**What it does:** Creates personal notes

**SDK API functions:**
- `note_create(user_id, mod_name, title, content)`
- `note_list(user_id)`
- `note_delete(note_id)`

---

### 3.7 Todo List

**What it does:** Creates personal todo items

**SDK API functions:**
- `todo_add(user_id, mod_name, task)`
- `todo_list(user_id)`
- `todo_complete(todo_id)`

---

### 3.8 Calculator

**What it does:** Saves calculation history

**SDK API functions:**
- `calc_save(user_id, expression, result)`

---

### 3.9 Market System

**What it does:** Allows players to sell items to other players (auction house)

**SDK API functions:**
- `market_sell(user_id, item_id, quantity, price)`
- `market_buy(buyer_id, market_id, quantity)`
- `market_cancel(user_id, market_id)`
- `market_list(guild_id, mod_name)`
- `market_my_listings(user_id)`

**Example workflow:**
1. Player A wants to sell an "Iron Sword" for 100 points
2. Player A runs `/sdk_sell item_id:1 price:100`
3. The item is listed on the market
4. Player B runs `/sdk_market` to browse
5. Player B runs `/sdk_buy market_id:5` to purchase

---

### 3.10 Guild System

**What it does:** Creates player guilds/clans

**SDK API functions:**
- `guild_create(guild_id, mod_name, name, description, leader_id)`
- `guild_join(guild_id, sdk_guild_id, user_id)`
- `guild_leave(guild_id, sdk_guild_id, user_id)`
- `guild_list(guild_id)`
- `guild_deposit(sdk_guild_id, user_id, amount)`

**Example workflow:**
1. Player A creates a guild: `/sdk_guild_create name:"Dragon Slayers"`
2. Player B joins: `/sdk_guild_join guild_id:1`
3. Members can donate to guild funds: `/sdk_guild_deposit guild_id:1 amount:100`

---

### 3.11 Wiki System

**What it does:** Creates a knowledge base / wiki

**SDK API functions:**
- `wiki_create_page(guild_id, mod_name, title, content, author_id, category)`
- `wiki_edit_page(page_id, title, content)`
- `wiki_delete_page(page_id)`
- `wiki_search(guild_id, keyword)`

**Example workflow:**
1. Create a page: `/sdk_wiki_create title:"Game Guide" content:"..."`
2. Search: `/sdk_wiki_search keyword:"guide"`

---

### 3.12 Automation System

**What it does:** Creates automated tasks (triggers and actions)

**SDK API functions:**
- `automation_create(guild_id, mod_name, name, trigger_type, trigger_config, action_config, creator_id)`
- `automation_enable(auto_id)`
- `automation_disable(auto_id)`
- `automation_delete(auto_id)`
- `automation_list(guild_id)`

**Trigger types:** `cron` (scheduled), `event` (user join, message, etc.)

**Example workflow:**
1. Create an automation: "Every day at 08:00, give all members 10 gold coins"
2. The bot will automatically execute this task

---

## 4. The `action` Field: Dynamic Commands

You can create dynamic commands that call SDK functions:

```json
{
  "name": "check_gold",
  "description": "Check my gold balance",
  "action": {
    "function": "currency_get_balance",
    "args": [{"var": "user_id"}, 1],
    "response": "Your gold balance: {result} 🟡"
  }
}
```

**Special variables:**
- `{"var": "user_id"}` → `interaction.user.id`
- `{"var": "guild_id"}` → `interaction.guild.id`
- `{"var": "channel_id"}` → `interaction.channel.id`

---

## 5. Debugging Tips

1. **Check bot console output:** Look for `[ModSDK] ...` logs
2. **Check database:** Use a SQLite browser to open `users.db`
3. **Test commands:** Use `/sdk_balance`, `/sdk_items`, etc.
4. **Check errors:** Errors are logged to console and shown in `/uploadmods` response

---

*Tutorial version: 1.1 | Updated: 2026-06-22*
