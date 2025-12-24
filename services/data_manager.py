"""
Data persistence manager for course tracking data.

This module handles loading and saving tracked courses and guild
channel configurations to/from JSON files.
"""

import json
import os
from typing import Dict
from models.course import TrackedCourse


class DataManager:
    """
    資料持久化管理器

    負責載入與儲存追蹤課程資料與伺服器頻道設定。
    """

    def __init__(self, data_file: str = "courses.json"):
        """
        初始化資料管理器

        Args:
            data_file: 資料檔案路徑
        """
        self.data_file = data_file
        self.guild_channels: Dict[int, int] = {}
        self._load()

    def _load(self) -> None:
        """從檔案載入資料"""
        if not os.path.exists(self.data_file):
            self.guild_channels = {}
            return

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 載入伺服器頻道設定
                self.guild_channels = {
                    int(guild_id): channel_id
                    for guild_id, channel_id in data.get("guild_channels", {}).items()
                }
        except Exception as e:
            print(f"❌ 載入資料失敗: {e}")
            self.guild_channels = {}

    def save(self, tracked_courses: Dict[int, Dict[str, TrackedCourse]]) -> bool:
        """
        儲存追蹤課程資料

        Args:
            tracked_courses: 追蹤課程字典 (guild_id -> {course_code -> TrackedCourse})

        Returns:
            True 如果儲存成功，否則 False
        """
        try:
            # 轉換為 JSON 可序列化格式
            data = {
                "tracked_courses": {
                    str(guild_id): {
                        course_code: course.to_dict()
                        for course_code, course in courses.items()
                    }
                    for guild_id, courses in tracked_courses.items()
                },
                "guild_channels": self.guild_channels
            }

            # 寫入檔案
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"❌ 儲存資料失敗: {e}")
            return False

    def load_tracked_courses(self) -> Dict[int, Dict[str, TrackedCourse]]:
        """
        載入追蹤課程資料

        Returns:
            追蹤課程字典 (guild_id -> {course_code -> TrackedCourse})
        """
        if not os.path.exists(self.data_file):
            return {}

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tracked_courses = {}

                for guild_id_str, courses_data in data.get("tracked_courses", {}).items():
                    guild_id = int(guild_id_str)
                    tracked_courses[guild_id] = {}

                    for course_code, course_data in courses_data.items():
                        tracked_courses[guild_id][course_code] = TrackedCourse.from_dict(
                            course_code,
                            course_data
                        )

                return tracked_courses
        except Exception as e:
            print(f"❌ 載入追蹤課程失敗: {e}")
            return {}

    async def restore_tracking(self, tracker) -> None:
        """
        恢復追蹤狀態（在 Bot 啟動時呼叫）

        Args:
            tracker: CourseTracker 實例
        """
        tracked_courses = self.load_tracked_courses()

        for guild_id, courses in tracked_courses.items():
            for course_code, course in courses.items():
                await tracker.start_tracking(guild_id, course_code, course)

        print(f"✅ 恢復追蹤 {sum(len(c) for c in tracked_courses.values())} 門課程")

    def set_guild_channel(self, guild_id: int, channel_id: int) -> None:
        """
        設定伺服器的通知頻道

        Args:
            guild_id: Discord 伺服器 ID
            channel_id: Discord 頻道 ID
        """
        self.guild_channels[guild_id] = channel_id

    def get_guild_channel(self, guild_id: int) -> int:
        """
        取得伺服器的通知頻道

        Args:
            guild_id: Discord 伺服器 ID

        Returns:
            頻道 ID，如果未設定則為 None
        """
        return self.guild_channels.get(guild_id)

    def remove_guild_channel(self, guild_id: int) -> bool:
        """
        移除伺服器的通知頻道設定

        Args:
            guild_id: Discord 伺服器 ID

        Returns:
            True 如果成功移除，False 如果不存在
        """
        if guild_id in self.guild_channels:
            del self.guild_channels[guild_id]
            return True
        return False
