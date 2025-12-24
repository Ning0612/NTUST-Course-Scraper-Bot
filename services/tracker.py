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

                # 更新課程資料
                course.name = course_info["course_name"]
                course.teacher = course_info["teacher_name"]
                course.lesson_time = course_info["lesson_time"]
                course.classroom = course_info["classroom"]
                course.remark = course_info["remark_text"]
                course.enrolled_students = course_info["enrolled_students"]

                # 檢查名額並發送通知
                if course.has_available_seats():
                    if not course.notified:
                        await self._send_notification(guild_id, course, course_info)
                        course.notified = True
                        self.debug_print(
                            f"📢 已發送 {course_code} 名額通知 "
                            f"({course.enrolled_students}/{course.max_students})"
                        )
                else:
                    # 名額已滿，重置通知狀態
                    course.notified = False

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

        Args:
            guild_id: Discord 伺服器 ID
            course: TrackedCourse 實例
            course_info: 課程資訊字典
        """
        channel_id = self.guild_channels.get(guild_id)
        if not channel_id:
            self.debug_print(f"⚠️ 伺服器 {guild_id} 未設定通知頻道")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            self.debug_print(f"⚠️ 找不到通知頻道 {channel_id}")
            return

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

        try:
            await channel.send(message)
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
