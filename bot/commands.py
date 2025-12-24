"""
Discord bot slash commands.

This module contains all Discord slash commands registered with the bot,
refactored to use the service layer (CourseTracker, DataManager, etc.).
"""

import discord
from discord import app_commands
from models.course import TrackedCourse
from services.api_client import get_course_info
from config.settings import debug_print


def setup_commands(bot, tracker, data_manager):
    """
    註冊所有斜線指令

    Args:
        bot: Discord Bot 實例
        tracker: CourseTracker 實例
        data_manager: DataManager 實例
    """

    @bot.tree.command(name="add", description="追蹤指定課程")
    async def add(interaction: discord.Interaction, course_code: str):
        """
        新增課程追蹤

        Args:
            interaction: Discord 互動
            course_code: 課程代碼（例如 "CS1006301"）
        """
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        debug_print(
            f"📩 收到追蹤請求: {interaction.user.name} ({user_id}) "
            f"@ {interaction.guild.name} ({guild_id}) - {course_code}"
        )

        await interaction.response.defer()

        # 檢查是否已追蹤該課程
        existing_course = tracker.get_course(guild_id, course_code)
        if existing_course:
            async with tracker.lock:
                was_new = existing_course.add_follower(user_id)
                data_manager.save(tracker.tracked_courses)

            if was_new:
                debug_print(f"✅ 將使用者 {user_id} 加入 {course_code} 的追蹤列表")
                await interaction.followup.send(
                    f"✅ 已將您加入 `{course_code}` 的追蹤列表。",
                    ephemeral=True
                )
            else:
                debug_print(f"⚠️ 使用者 {user_id} 已在 {course_code} 的追蹤列表中")
                await interaction.followup.send(
                    f"⚠️ 你已經在追蹤 `{course_code}`！",
                    ephemeral=True
                )
            return

        # 使用 API 驗證課程
        debug_print(f"🔍 正在驗證課程 {course_code}")
        details = await get_course_info(course_code)

        if details is None:
            debug_print(f"📤 通知使用者找不到課程 {course_code}")
            await interaction.followup.send(
                f"⚠️ **找不到課程 `{course_code}`！**\n請檢查課程代碼是否正確，或稍後再試。",
                ephemeral=True
            )
            return

        # 建立追蹤
        course = TrackedCourse(
            code=course_code,
            name=details["course_name"],
            teacher=details["teacher_name"],
            lesson_time=details["lesson_time"],
            classroom=details["classroom"],
            remark=details["remark_text"],
            enrolled_students=details["enrolled_students"],
            max_students=details["max_students"],
            notified=False,
            followers={user_id}
        )

        await tracker.start_tracking(guild_id, course_code, course)
        data_manager.save(tracker.tracked_courses)

        debug_print(
            f"✅ 成功創建追蹤：{course_code} "
            f"({course.enrolled_students}/{course.max_students})"
        )
        await interaction.followup.send(
            f"✅ 已成功找到並開始追蹤課程：\n"
            f"**`{course.code} - {course.name} "
            f"({course.enrolled_students}/{course.max_students})`**"
        )

    @bot.tree.command(name="del", description="取消追蹤課程")
    async def delete_course(interaction: discord.Interaction, course_code: str):
        """
        取消課程追蹤

        Args:
            interaction: Discord 互動
            course_code: 課程代碼
        """
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        debug_print(
            f"📩 收到取消追蹤請求: {interaction.user.name} ({user_id}) "
            f"@ {interaction.guild.name} ({guild_id}) - {course_code}"
        )

        course = tracker.get_course(guild_id, course_code)
        if not course:
            debug_print(f"⚠️ 使用者嘗試取消未追蹤的課程 {course_code}")
            await interaction.response.send_message(
                f"⚠️ 你未追蹤 `{course_code}`！"
            )
            return

        # 移除追蹤者
        was_removed = await tracker.stop_tracking(guild_id, course_code, user_id)
        data_manager.save(tracker.tracked_courses)

        if was_removed:
            debug_print(f"🗑️ 完全移除課程 {course_code}（無追蹤者）")
        else:
            debug_print(f"✅ 從 {course_code} 移除使用者 {user_id}")

        await interaction.response.send_message(f"✅ 你已取消追蹤 `{course_code}`")

    @bot.tree.command(name="list", description="列出此伺服器追蹤中的課程")
    async def list_courses(interaction: discord.Interaction):
        """
        列出所有追蹤中的課程

        Args:
            interaction: Discord 互動
        """
        guild_id = interaction.guild.id

        debug_print(
            f"📩 收到課程列表請求: {interaction.user.name} ({interaction.user.id}) "
            f"@ {interaction.guild.name} ({guild_id})"
        )

        courses = tracker.get_tracked_courses(guild_id)
        if not courses:
            debug_print("📤 該伺服器無追蹤中的課程")
            await interaction.response.send_message("⚠️ 目前此伺服器無追蹤中的課程！")
            return

        # 建立課程訊息列表
        message_list = []
        for code, course in courses.items():
            # 取得追蹤者名稱
            followers_list = []
            for user_id in course.followers:
                try:
                    user = await bot.fetch_user(user_id)
                    followers_list.append(user.name)
                except:
                    followers_list.append(f"<@{user_id}>")

            followers = ", ".join(followers_list) or "無人追蹤"

            message_list.append(
                f"📌 `{code}` - {course.name}\n"
                f"👨‍🏫 **教師:** {course.teacher}\n"
                f"🕒 **時間:** {course.lesson_time}\n"
                f"📍 **教室:** {course.classroom}\n"
                f"📌 **目前人數:** {course.enrolled_students}/{course.max_students}\n"
                f"👥 **追蹤者:** {followers}\n"
                f"🔹🔹🔹🔹🔹"
            )

        # 分割訊息（Discord 限制 2000 字元）
        message_chunks = []
        current_chunk = ""
        for line in message_list:
            if len(current_chunk) + len(line) + 1 > 2000:
                message_chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += line + "\n"
        if current_chunk:
            message_chunks.append(current_chunk)

        # 發送訊息
        debug_print(f"📤 發送課程列表 ({len(message_chunks)} 個訊息)")
        for i, msg in enumerate(message_chunks):
            if i == 0:
                await interaction.response.send_message(msg)
            else:
                await interaction.followup.send(msg)

    @bot.tree.command(name="set_channel", description="設定通知頻道")
    async def set_channel(interaction: discord.Interaction):
        """
        設定當前頻道為通知頻道

        Args:
            interaction: Discord 互動
        """
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        debug_print(
            f"📩 收到設定通知頻道請求: {interaction.user.name} ({interaction.user.id}) "
            f"@ {interaction.guild.name} ({guild_id}) - #{interaction.channel.name} ({channel_id})"
        )

        data_manager.set_guild_channel(guild_id, channel_id)
        # 更新 tracker 的 guild_channels
        tracker.guild_channels[guild_id] = channel_id
        data_manager.save(tracker.tracked_courses)

        debug_print(f"✅ 設定通知頻道為 #{interaction.channel.name} ({channel_id})")
        await interaction.response.send_message("✅ 此頻道已設定為通知頻道！")

    @bot.tree.command(name="help", description="顯示所有指令的說明")
    async def help_command(interaction: discord.Interaction):
        """
        顯示幫助訊息

        Args:
            interaction: Discord 互動
        """
        debug_print(
            f"📩 收到說明指令請求: {interaction.user.name} ({interaction.user.id}) "
            f"@ {interaction.guild.name} ({interaction.guild.id})"
        )

        embed = discord.Embed(
            title="🤖 機器人指令說明",
            description="以下是所有可用的斜線指令：",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="`/add <course_code>`",
            value="開始追蹤一個新的課程。",
            inline=False
        )
        embed.add_field(
            name="`/del <course_code>`",
            value="取消追蹤一個指定的課程。",
            inline=False
        )
        embed.add_field(
            name="`/list`",
            value="列出此伺服器上所有正在追蹤的課程。",
            inline=False
        )
        embed.add_field(
            name="`/set_channel`",
            value="將目前的頻道設為接收通知的頻道。",
            inline=False
        )
        embed.add_field(
            name="`/help`",
            value="顯示這則說明訊息。",
            inline=False
        )
        embed.add_field(
            name="GitHub 原始碼",
            value="[NTUST Course Scraper Bot](https://github.com/Ning0612/NTUST-Course-Scraper-Bot)",
            inline=False
        )
        embed.set_footer(text="NTUST Course Scraper Bot v2.0 (Phase 2)")

        debug_print(f"📤 發送說明訊息")
        await interaction.response.send_message(embed=embed, ephemeral=True)
