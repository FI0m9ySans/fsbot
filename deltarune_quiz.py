"""
Deltarune 第五章 互动问答 — 真正的 Quiz！
使用 Discord UI 按钮，每道题限时20秒，答对得分
"""
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random

# ═══════════════════════════════════════════
# 题库（正确答案 index=0）
# ═══════════════════════════════════════════

QUIZ_QUESTIONS = [
    {
        "q": "🥚 被遗忘的男人在蛋房间里说，周日要去干什么？",
        "options": ["收割麦子 🌾", "去教堂 🙏", "找 Susie 玩 🎮", "睡觉 😴"],
        "answer": 0,
        "hint": "第五章的时间线正好是周日…"
    },
    {
        "q": "🎪 第五章的主题是什么？",
        "options": ["周末庆典 🎪", "生日派对 🎂", "婚礼 💒", "丰收节 🌽"],
        "answer": 0,
        "hint": "光世界正在举办活动！"
    },
    {
        "q": "📺 未使用曲 Sneaking 关联哪两个角色？",
        "options": ["Mike 和 Tenna 📺", "Spamton 和 Jevil 🃏", "Kris 和 Susie ⚔️", "Asgore 和 Toriel 💔"],
        "answer": 0,
        "hint": "Toby Fox 在通讯中暗示过 Mike 的剧情"
    },
    {
        "q": "👑 根据预言壁挂，谁是第五章的关键人物？",
        "options": ["Asgore Dreemurr 👑", "Tenna 📺", "Mike 🎤", "Seam 🧵"],
        "answer": 0,
        "hint": "他曾是暗世界的国王…"
    },
    {
        "q": "💎 Seam 收集了几颗暗影水晶？",
        "options": ["五颗 💎💎💎💎💎", "三颗 💎💎💎", "一颗 💎", "七颗 💎💎💎💎💎💎💎"],
        "answer": 0,
        "hint": "每章一颗，加上第三章…"
    },
    {
        "q": "❄️ 怪异路线（Weird Route）在哪个章节有重大影响？",
        "options": ["第四章 → 第五章 🔗", "第二章 → 第三章 🔗", "只在第四章 ❄️", "不影响第五章 ❌"],
        "answer": 0,
        "hint": "第四章的结局直接延续到第五章"
    },
    {
        "q": "🏰 城堡镇（Castle Town）在第几章关闭后重新开放？",
        "options": ["第三章 🏰", "第二章 🌃", "第四章 ❄️", "一直开放 🎪"],
        "answer": 0,
        "hint": "第三章之后我们暂时回不去了…"
    },
    {
        "q": "🎵 新店主的主题曲叫什么？",
        "options": ["Shop 3 🎶", "Spamton's Theme 📞", "Raise Up Your Bat ⚾", "Sneaking 📺"],
        "answer": 0,
        "hint": "Toby 说这是唯一一首没剧透东西的音乐"
    },
]

POINTS_PER_Q = 20
TOTAL_QUESTIONS = 5
QUESTION_TIMEOUT = 20  # 秒


# ═══════════════════════════════════════════
# UI 组件
# ═══════════════════════════════════════════

class OptionButton(Button):
    """答题选项按钮"""
    def __init__(self, label: str, option_index: int, correct_index: int, parent_view: View):
        # 默认灰色，答后变色
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.option_index = option_index
        self.correct_index = correct_index
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.on_answer(interaction, self.option_index)


class QuizView(View):
    """单道题的视图"""
    def __init__(self, question_data: dict, q_num: int, total: int):
        super().__init__(timeout=QUESTION_TIMEOUT)
        self.question_data = question_data
        self.q_num = q_num
        self.total = total
        self.answered = False
        self.correct_index = question_data["answer"]

        # 打乱选项顺序
        options = question_data["options"].copy()
        random.shuffle(options)
        self.shuffled_options = options
        self.shuffled_correct_index = options.index(question_data["options"][self.correct_index])

        for i, opt in enumerate(options):
            self.add_item(OptionButton(
                label=opt,
                option_index=i,
                correct_index=self.shuffled_correct_index,
                parent_view=self
            ))

    async def on_answer(self, interaction: discord.Interaction, chosen_index: int):
        if self.answered:
            await interaction.response.send_message("⚠️ 你已经答过了！", ephemeral=True)
            return

        self.answered = True
        self.stop()

        is_correct = (chosen_index == self.shuffled_correct_index)

        # 给按钮上色
        for child in self.children:
            if isinstance(child, OptionButton):
                if child.option_index == self.shuffled_correct_index:
                    child.style = discord.ButtonStyle.success
                elif child.option_index == chosen_index and not is_correct:
                    child.style = discord.ButtonStyle.danger
                child.disabled = True

        if is_correct:
            from mod_sdk import SDK_API
            user_id = interaction.user.id
            SDK_API["add_points"](user_id, POINTS_PER_Q)
            current_pts = SDK_API["get_points"](user_id)

            embed = discord.Embed(
                title="✅ 回答正确！",
                description=f"**{self.question_data['q']}**\n\n"
                            f"正确答案：**{self.question_data['options'][self.correct_index]}**\n\n"
                            f"🎁 +**{POINTS_PER_Q} 积分**！（当前：{current_pts}）",
                color=discord.Color.green()
            )
        else:
            correct_text = self.question_data["options"][self.correct_index]
            embed = discord.Embed(
                title="❌ 回答错误…",
                description=f"**{self.question_data['q']}**\n\n"
                            f"正确答案：**{correct_text}**\n"
                            f"💡 提示：{self.question_data['hint']}",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        # 超时未答，禁用所有按钮并标出正确答案
        for child in self.children:
            if isinstance(child, OptionButton):
                if child.option_index == self.shuffled_correct_index:
                    child.style = discord.ButtonStyle.success
                child.disabled = True


class StartView(View):
    """开始答题的视图"""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="▶ 开始答题！", style=discord.ButtonStyle.primary, emoji="🎯")
    async def start_btn(self, interaction: discord.Interaction, button: Button):
        button.disabled = True
        button.label = "答题中…"
        await interaction.response.edit_message(content="🎯 答题即将开始！", view=self)
        # 在新消息里发第一题
        await run_quiz(interaction, interaction.user)


# ═══════════════════════════════════════════
# 问答流程
# ═══════════════════════════════════════════

async def run_quiz(interaction: discord.Interaction, player: discord.Member):
    """运行完整的问答流程"""
    questions = random.sample(QUIZ_QUESTIONS, min(TOTAL_QUESTIONS, len(QUIZ_QUESTIONS)))
    correct_count = 0

    for i, q_data in enumerate(questions):
        view = QuizView(q_data, i + 1, len(questions))
        embed = discord.Embed(
            title=f"❓ 第 {i + 1}/{len(questions)} 题",
            description=f"**{q_data['q']}**\n\n点击按钮选择答案！（{QUESTION_TIMEOUT}秒内）",
            color=discord.Color.blurple()
        )
        # 第一题用 followup，后续用 channel.send
        if i == 0:
            msg = await interaction.followup.send(embed=embed, view=view)
        else:
            msg = await interaction.channel.send(embed=embed, view=view)

        # 等待回答或超时
        await view.wait()

        if not view.answered:
            # 超时
            timeout_embed = discord.Embed(
                title="⏰ 时间到！",
                description=f"正确答案：**{q_data['options'][q_data['answer']]}**\n"
                            f"💡 提示：{q_data['hint']}",
                color=discord.Color.orange()
            )
            await msg.edit(embed=timeout_embed, view=view)
        else:
            # 答对计数
            # 需要从 view 里判断（on_answer 里已处理）
            # 这里简单判断：如果 answered=True 且按钮正确，在 on_answer 里已加分
            pass

    # 最终得分
    from mod_sdk import SDK_API
    total_pts = SDK_API["get_points"](player.id)

    # 重新计算答对数量（通过查看每个 view 的 answered 状态）
    # 简化：直接显示参与奖励
    embed = discord.Embed(
        title="🏁 答题结束！",
        description=f"**{player.display_name}** 感谢参与 Deltarune 第五章庆贺问答！\n\n"
                    f"🎁 每题 **{POINTS_PER_Q} 积分**，答对即得！\n"
                    f"💰 当前总积分：**{total_pts}**\n\n"
                    f"🎉 快去玩第五章吧！",
        color=discord.Color.gold()
    )
    await interaction.channel.send(embed=embed)


# ═══════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════

class DeltaruneQuiz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="deltarune_quiz", description="🎯 Deltarune 第五章 互动问答！答对得分")
    async def deltarune_quiz(self, interaction: discord.Interaction):
        """启动互动问答"""
        view = StartView()
        await interaction.response.send_message(
            "🎯 **Deltarune 第五章 互动问答** 准备开始！\n"
            f"📋 共 **{TOTAL_QUESTIONS} 道题**，每题 **{POINTS_PER_Q} 积分**，限时 **{QUESTION_TIMEOUT} 秒**！\n"
            "⚠️ 含剧透，建议通关后再玩~\n\n"
            "**按按钮开始！**",
            view=view
        )


# ═══════════════════════════════════════════
# 注册函数
# ═══════════════════════════════════════════

async def init_quiz(bot: commands.Bot):
    await bot.add_cog(DeltaruneQuiz(bot))
    print("[DeltaruneQuiz] 问答模块已加载 ✅")
