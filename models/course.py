"""
Course data model for tracking course information.

This module provides the TrackedCourse dataclass that represents
a course being tracked by the bot with all its metadata.
"""

from dataclasses import dataclass, field
from typing import Set


@dataclass
class TrackedCourse:
    """
    課程追蹤資料模型

    代表一個正在被追蹤的課程，包含所有課程資訊與追蹤狀態。
    """

    code: str
    name: str
    teacher: str
    lesson_time: str
    classroom: str
    remark: str
    enrolled_students: int
    max_students: int
    notified: bool
    followers: Set[int] = field(default_factory=set)

    def to_dict(self) -> dict:
        """
        轉為 JSON 可序列化格式

        Returns:
            包含所有課程資料的字典
        """
        return {
            "name": self.name,
            "teacher": self.teacher,
            "lesson_time": self.lesson_time,
            "classroom": self.classroom,
            "remark": self.remark,
            "enrolled_students": self.enrolled_students,
            "max_students": self.max_students,
            "notified": self.notified,
            "followers": list(self.followers)
        }

    @classmethod
    def from_dict(cls, code: str, data: dict) -> 'TrackedCourse':
        """
        從 JSON 載入課程資料

        Args:
            code: 課程代碼
            data: 包含課程資料的字典

        Returns:
            TrackedCourse 實例
        """
        return cls(
            code=code,
            name=data["name"],
            teacher=data["teacher"],
            lesson_time=data["lesson_time"],
            classroom=data["classroom"],
            remark=data["remark"],
            enrolled_students=data["enrolled_students"],
            max_students=data["max_students"],
            notified=data["notified"],
            followers=set(data["followers"])
        )

    def has_available_seats(self) -> bool:
        """
        檢查是否有空位

        Returns:
            True 如果有空位，否則 False
        """
        return self.enrolled_students < self.max_students

    def add_follower(self, user_id: int) -> bool:
        """
        新增追蹤者

        Args:
            user_id: Discord 使用者 ID

        Returns:
            True 如果成功新增（之前不存在），False 如果已存在
        """
        if user_id in self.followers:
            return False
        self.followers.add(user_id)
        return True

    def remove_follower(self, user_id: int) -> bool:
        """
        移除追蹤者

        Args:
            user_id: Discord 使用者 ID

        Returns:
            True 如果成功移除，False 如果不存在
        """
        if user_id not in self.followers:
            return False
        self.followers.remove(user_id)
        return True

    def has_followers(self) -> bool:
        """
        檢查是否有追蹤者

        Returns:
            True 如果有至少一個追蹤者
        """
        return len(self.followers) > 0
