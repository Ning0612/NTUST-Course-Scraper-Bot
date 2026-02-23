"""
Course tracker service for managing course monitoring.

This module provides the CourseTracker class that centralizes all
course tracking logic, using a Worker Pool for efficient concurrent queries.
"""

import asyncio
from typing import Dict, Callable
from models.course import TrackedCourse
from services.api_client import get_course_info
from services.worker_pool import WorkerPool


def find_writable_channel(guild, bot_user_id):
    """
    在伺服器中尋找第一個 Bot 具備發送訊息權限的文字頻道

    Args:
        guild: Discord Guild 實例
        bot_user_id: Bot 的使用者 ID

    Returns:
        discord.TextChannel 或 None
    """
    # 優先嘗試系統頻道
    if guild.system_channel:
        me = guild.me or guild.get_member(bot_user_id)
        if me and guild.system_channel.permissions_for(me).send_messages:
            return guild.system_channel

    # 否則尋找第一個可寫入的文字頻道
    for channel in guild.text_channels:
        me = guild.me or guild.get_member(bot_user_id)
        if me and channel.permissions_for(me).send_messages:
            return channel
    return None


class CourseTracker:
    """
    課程追蹤管理器（使用 Worker Pool）

    取代原本「每課程一任務」的模式，使用單一輪詢任務配合 Worker Pool
    並行查詢所有課程，大幅降低記憶體使用與系統負擔。
    """

    def __init__(
        self,
        bot,
        guild_channels: Dict[int, int],
        worker_pool: WorkerPool,
        debug_print: Callable
    ):
        """
        初始化課程追蹤器

        Args:
            bot: Discord Bot 實例
            guild_channels: 伺服器 ID -> 通知頻道 ID 的映射
            worker_pool: Worker Pool 實例
            debug_print: 除錯輸出函數
        """
        self.bot = bot
        self.guild_channels = guild_channels
        self.worker_pool = worker_pool
        self.debug_print = debug_print
        self.tracked_courses: Dict[int, Dict[str, TrackedCourse]] = {}
        self.warned_guilds = set()  # 記錄已發送權限警告的伺服器，避免重複洗板
        self.lock = asyncio.Lock()
        self.polling_task = None

    async def start_tracking(
        self,
        guild_id: int,
        course_code: str,
        course: TrackedCourse
    ) -> None:
        """
        開始追蹤課程（不建立獨立任務）

        Args:
            guild_id: Discord 伺服器 ID
            course_code: 課程代碼
            course: TrackedCourse 實例
        """
        async with self.lock:
            if guild_id not in self.tracked_courses:
                self.tracked_courses[guild_id] = {}
            self.tracked_courses[guild_id][course_code] = course
            self.debug_print(f"✅ 開始追蹤課程 {course_code} (伺服器 {guild_id})")

    async def stop_tracking(self, guild_id: int, course_code: str, user_id: int) -> bool:
        """
        停止追蹤課程（移除追蹤者）

        Args:
            guild_id: Discord 伺服器 ID
            course_code: 課程代碼
            user_id: 使用者 ID

        Returns:
            True 如果課程已完全移除（無追蹤者），否則 False
        """
        async with self.lock:
            if guild_id not in self.tracked_courses:
                return False
            if course_code not in self.tracked_courses[guild_id]:
                return False

            course = self.tracked_courses[guild_id][course_code]
            course.remove_follower(user_id)

            # 如果沒有追蹤者了，完全移除課程
            if not course.has_followers():
                del self.tracked_courses[guild_id][course_code]
                self.debug_print(f"🗑️ 完全移除課程 {course_code} (無追蹤者)")
                return True

            return False

    async def start_polling(self, interval: int = 10) -> None:
        """
        啟動輪詢任務（單一背景任務處理所有課程）

        Args:
            interval: 輪詢間隔（秒），預設 10 秒
        """
        if self.polling_task is not None:
            self.debug_print("⚠️ 輪詢任務已在執行中")
            return

        self.polling_task = asyncio.create_task(self._polling_loop(interval))
        self.debug_print(f"🔄 啟動課程輪詢任務 (間隔 {interval} 秒)")

    async def stop_polling(self) -> None:
        """停止輪詢任務"""
        if self.polling_task is not None:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
            self.polling_task = None
            self.debug_print("⏹️ 停止課程輪詢任務")

    async def _polling_loop(self, interval: int) -> None:
        """
        輪詢所有追蹤的課程

        Args:
            interval: 輪詢間隔（秒）
        """
        while True:
            try:
                # 取得所有需要檢查的課程
                async with self.lock:
                    courses_to_check = [
                        (guild_id, course_code, course)
                        for guild_id, courses in self.tracked_courses.items()
                        for course_code, course in courses.items()
                    ]

                # 並行查詢所有課程（透過 Worker Pool）
                if courses_to_check:
                    tasks = [
                        self.worker_pool.submit(
                            self._check_course,
                            guild_id,
                            course_code,
                            course
                        )
                        for guild_id, course_code, course in courses_to_check
                    ]

                    # 等待所有查詢完成
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                self.debug_print(f"❌ 輪詢錯誤: {e}")

            # 等待下一次輪詢
            await asyncio.sleep(interval)

    async def _check_course(
        self,
        guild_id: int,
        course_code: str,
        course: TrackedCourse
    ) -> None:
        """
        檢查單一課程（由 Worker 執行）

        Args:
            guild_id: Discord 伺服器 ID
            course_code: 課程代碼
            course: TrackedCourse 實例
        """
        try:
            # 查詢課程資訊
            course_info = await get_course_info(course_code)

            if not course_info:
                self.debug_print(f"⚠️ 查詢課程 {course_code} 失敗，將重試")
                return

            # 更新課程資訊
            async with self.lock:
                # 再次確認課程仍在追蹤中（可能在查詢期間被移除）
                if guild_id not in self.tracked_courses:
                    return
                if course_code not in self.tracked_courses[guild_id]:
                    return

                # 更新課程資料 (加上欄位存在性檢查)
                course.name = course_info.get("course_name", course.name)
                course.teacher = course_info.get("teacher_name", course.teacher)
                course.lesson_time = course_info.get("lesson_time", course.lesson_time)
                course.classroom = course_info.get("classroom", course.classroom)
                course.remark = course_info.get("remark_text", course.remark)
                course.enrolled_students = course_info.get("enrolled_students", course.enrolled_students)

                # 檢查名額並標記通知狀態
                should_notify = False
                if course.has_available_seats():
                    if not course.notified:
                        # 標記為已通知以釋放鎖，避免重複發送
                        course.notified = True
                        should_notify = True
                else:
                    # 名額已滿，重置通知狀態
                    course.notified = False

            # 在鎖外執行 Discord API 呼叫，避免阻塞其他任務
            if should_notify:
                await self._send_notification(guild_id, course, course_info)
                self.debug_print(
                    f"📢 已發送 {course_code} 名額通知 "
                    f"({course.enrolled_students}/{course.max_students})"
                )

        except Exception as e:
            self.debug_print(f"❌ 檢查課程 {course_code} 時發生錯誤：{e}")

    async def _send_notification(
        self,
        guild_id: int,
        course: TrackedCourse,
        course_info: dict
    ) -> None:
        """
        發送名額通知

        優先使用已設定的通知頻道，若未設定則嘗試使用系統頻道。

        Args:
            guild_id: Discord 伺服器 ID
            course: TrackedCourse 實例
            course_info: 課程資訊字典
        """
        channel_id = self.guild_channels.get(guild_id)
        channel = None
        use_system_channel = False

        # 優先使用已設定的通知頻道
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                self.debug_print(f"⚠️ 找不到通知頻道 {channel_id}，嘗試使用系統頻道")

        # 未設定通知頻道或頻道不存在，嘗試使用系統頻道
        if not channel:
            guild = self.bot.get_guild(guild_id)
            if guild and guild.system_channel:
                channel = guild.system_channel
                use_system_channel = True
                self.debug_print(
                    f"⚠️ 伺服器 {guild_id} 未設定通知頻道，"
                    f"使用系統頻道 #{guild.system_channel.name} ({guild.system_channel.id})"
                )
            else:
                self.debug_print(
                    f"❌ 伺服器 {guild_id} 未設定通知頻道且無系統頻道，無法發送通知"
                )
                
                # 嘗試在其他有權限的頻道發送「未設定頻道」警告
                if guild_id not in self.warned_guilds:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        fallback_channel = find_writable_channel(guild, self.bot.user.id)
                        if fallback_channel:
                            warning_msg = (
                                f"⚠️ **未設定通知頻道警告**\n"
                                f"本伺服器尚未設定課程通知頻道，導致無法發送選課名額通知。\n"
                                f"請管理員使用 `/set_channel` 指令在目標頻道中設定專屬通知頻道。"
                            )
                            try:
                                await fallback_channel.send(warning_msg)
                                self.warned_guilds.add(guild_id)
                                self.debug_print(f"✅ 已在可用頻道 #{fallback_channel.name} 發送設定警告")
                            except Exception as e:
                                self.debug_print(f"❌ 在備用頻道發送警告失敗: {e}")
                return

        # 權限檢查 (安全取得自身成員對象)
        me = channel.guild.me or channel.guild.get_member(self.bot.user.id)
        if not me:
            self.debug_print(f"❌ 找不到 Bot 在伺服器 {guild_id} 的成員對象")
            return

        permissions = channel.permissions_for(me)
        if not permissions.send_messages:
            self.debug_print(
                f"❌ 權限不足: 伺服器 {guild_id} 的頻道 "
                f"#{channel.name} ({channel.id}) 缺少發送訊息權限，無法發送通知"
            )

            # 嘗試在其他有權限的頻道發送警告
            if guild_id not in self.warned_guilds:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    fallback_channel = find_writable_channel(guild, self.bot.user.id)
                    if fallback_channel and fallback_channel.id != channel.id:
                        warning_msg = (
                            f"⚠️ **權限不足警告**\n"
                            f"Bot 目前在設定的選課通知頻道 <#{channel.id}> 中缺少「發送訊息」權限，"
                            f"導致無法正常發送課程名額通知。\n"
                            f"請管理員檢查頻道權限設定，或使用 `/set_channel` 重新設定頻道。"
                        )
                        try:
                            await fallback_channel.send(warning_msg)
                            self.warned_guilds.add(guild_id)
                            self.debug_print(f"✅ 已在備用頻道 #{fallback_channel.name} 發送權限警告")
                        except Exception as e:
                            self.debug_print(f"❌ 在備用頻道發送警告失敗: {e}")
            return

        # 權限正常，重置警告狀態
        if guild_id in self.warned_guilds:
            self.warned_guilds.remove(guild_id)

        # 生成追蹤者提及字串
        followers = " ".join(f"<@{user_id}>" for user_id in course.followers)

        # 建立通知訊息
        message = (
            f"{followers} 🎉 **{course.code} {course.name}** 有名額！\n"
            f"👨‍🏫 **授課教師:** {course.teacher}\n"
            f"🕒 **時間:** {course.lesson_time}\n"
            f"📍 **教室:** {course.classroom}\n"
            f"📌 **目前人數:** {course.enrolled_students}/{course.max_students}\n"
            f"🔗 [前往選課](https://courseselection.ntust.edu.tw/AddAndSub/B01/B01)"
        )

        # 如果使用系統頻道，附加設定提示
        if use_system_channel:
            message += (
                f"\n\n💡 **提示：** 此訊息發送至系統頻道，"
                f"請管理員在適當的頻道中執行 `/set_channel` 設定專屬的課程通知頻道。"
            )

        try:
            await channel.send(message)
            self.debug_print(
                f"✅ 成功發送通知到 "
                f"{'系統頻道' if use_system_channel else '通知頻道'} #{channel.name}"
            )
        except Exception as e:
            self.debug_print(f"❌ 發送通知失敗: {e}")

    def get_tracked_courses(self, guild_id: int) -> Dict[str, TrackedCourse]:
        """
        取得指定伺服器的追蹤課程

        Args:
            guild_id: Discord 伺服器 ID

        Returns:
            課程代碼 -> TrackedCourse 的字典
        """
        return self.tracked_courses.get(guild_id, {})

    def get_course(self, guild_id: int, course_code: str) -> TrackedCourse:
        """
        取得指定課程

        Args:
            guild_id: Discord 伺服器 ID
            course_code: 課程代碼

        Returns:
            TrackedCourse 實例，如果不存在則為 None
        """
        return self.tracked_courses.get(guild_id, {}).get(course_code)

    async def clear_all_courses(self) -> int:
        """
        清除所有追蹤課程（所有伺服器）

        通常用於學期更新時自動清除過期課程。

        Returns:
            清除的課程數量
        """
        async with self.lock:
            total_cleared = sum(
                len(courses) for courses in self.tracked_courses.values()
            )
            self.tracked_courses.clear()
            self.debug_print(f"🗑️ 已清除所有追蹤課程（共 {total_cleared} 門）")
            return total_cleared
