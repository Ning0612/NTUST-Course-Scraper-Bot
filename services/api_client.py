"""
API client wrapper for querying NTUST course information.

This module provides async wrappers around the ntust_api module,
making it easy to integrate with async Discord bot code.
"""

import asyncio
from typing import Optional, Dict, Any
from ntust_api import CourseQueryClient


# Global API client instance
_api_client: Optional[CourseQueryClient] = None


def init_api_client() -> None:
    """
    初始化 API Client

    必須在使用 get_course_info() 之前呼叫。
    """
    global _api_client
    _api_client = CourseQueryClient()


async def get_course_info(course_code: str) -> Optional[Dict[str, Any]]:
    """
    使用 Course_API 查詢課程資訊（非同步）

    Args:
        course_code: 課程代碼（例如 "CS1006301"）

    Returns:
        包含課程資訊的字典，如果查詢失敗則回傳 None

        字典格式：
        {
            "course_code": str,
            "course_name": str,
            "teacher_name": str,
            "lesson_time": str,
            "classroom": str,
            "remark_text": str,
            "enrolled_students": int,
            "max_students": int
        }
    """
    if _api_client is None:
        raise RuntimeError("API Client not initialized. Call init_api_client() first.")

    try:
        # API 呼叫是同步的，需要在 executor 中執行避免阻塞事件循環
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            _api_client.search_courses,
            None,  # semester (自動取得最新)
            course_code
        )

        if not results:
            return None

        course = results[0]
        return {
            "course_code": course.get("CourseNo", ""),
            "course_name": course.get("CourseName", ""),
            "teacher_name": course.get("CourseTeacher", ""),
            "lesson_time": course.get("Node", ""),
            "classroom": course.get("ClassRoomNo", ""),
            "remark_text": course.get("Contents", ""),
            "enrolled_students": int(course.get("ChooseStudent", 0)),
            "max_students": int(course.get("Restrict2", 0))
        }
    except Exception as e:
        # 錯誤處理由呼叫者決定
        print(f"❌ API 查詢失敗 {course_code}: {e}")
        return None


async def search_courses(
    semester: Optional[str] = None,
    course_no: Optional[str] = None,
    course_name: Optional[str] = None,
    teacher: Optional[str] = None
) -> list:
    """
    搜尋課程（進階查詢）

    Args:
        semester: 學期代碼（None 為最新學期）
        course_no: 課程代碼
        course_name: 課程名稱
        teacher: 授課教師

    Returns:
        課程列表
    """
    if _api_client is None:
        raise RuntimeError("API Client not initialized. Call init_api_client() first.")

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            _api_client.search_courses,
            semester,
            course_no,
            course_name,
            teacher
        )
        return results
    except Exception as e:
        print(f"❌ 搜尋課程失敗: {e}")
        return []
