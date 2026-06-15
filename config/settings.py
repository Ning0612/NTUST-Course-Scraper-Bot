"""
Configuration settings for NTUST Course Tracker Bot.

This module centralizes environment variable access and provides
default values for all configuration options.
"""

import os
import datetime
from typing import List, Optional, Tuple
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 台北時區（Asia/Taipei，UTC+8，台灣不使用夏令時）
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    TAIPEI_TZ = _ZoneInfo("Asia/Taipei")
except Exception:
    TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))


class Settings:
    """Bot 配置設定"""

    # Discord Bot Token
    TOKEN: str = os.getenv("TOKEN", "")

    # 除錯模式
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Worker Pool 大小
    WORKER_POOL_SIZE: int = int(os.getenv("WORKER_POOL_SIZE", "5"))

    # 課程查詢間隔（秒）
    POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "10"))

    # 定期通知間隔（分鐘）
    NOTIFICATION_INTERVAL: int = int(os.getenv("NOTIFICATION_INTERVAL", "1"))

    # 資料檔案路徑
    DATA_FILE: str = os.getenv("DATA_FILE", "courses.json")

    # 選課期間設定（格式：MM-DD~MM-DD，多組用逗號分隔）
    # 例如：03-17~03-28,09-15~10-05（上下學期各一組）
    TRACKING_PERIODS_STR: str = os.getenv("TRACKING_PERIODS", "")

    @staticmethod
    def _parse_md(s: str) -> Optional[Tuple[int, int]]:
        """
        解析 MM-DD 字串為 (month, day)，失敗回傳 None

        Args:
            s: MM-DD 格式的日期字串

        Returns:
            (month, day) tuple 或 None
        """
        try:
            parts = s.strip().split("-")
            if len(parts) != 2:
                return None
            m, d = int(parts[0]), int(parts[1])
            datetime.date(2001, m, d)  # 驗證合法性（非閏年）
            return (m, d)
        except ValueError:
            return None

    @staticmethod
    def get_tracking_periods() -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        解析 TRACKING_PERIODS，回傳所有選課期間 pair 清單

        Returns:
            [(start_md, end_md), ...] 例如 [((3,17),(3,28)), ((9,15),(10,5))]
        """
        raw = Settings.TRACKING_PERIODS_STR.strip()
        if not raw:
            return []
        result = []
        for pair_str in raw.split(","):
            pair_str = pair_str.strip()
            if not pair_str:
                continue
            parts = pair_str.split("~")
            if len(parts) != 2:
                print(f"⚠️ 無效的追蹤期間格式 '{pair_str}'（應為 MM-DD~MM-DD），已略過")
                continue
            start = Settings._parse_md(parts[0])
            end = Settings._parse_md(parts[1])
            if start is None or end is None:
                print(f"⚠️ 無效的日期 '{pair_str}'，已略過")
                continue
            result.append((start, end))
        return result

    @staticmethod
    def get_active_period(
        today: datetime.date
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        回傳今天所在的選課期間，若無則回傳 None

        同年區間（start <= end）：start <= today <= end
        跨年區間（start > end）：today >= start(今年) 或 today <= end(今年)

        Args:
            today: 要檢查的日期

        Returns:
            (start_md, end_md) tuple 或 None
        """
        year = today.year
        for (sm, sd), (em, ed) in Settings.get_tracking_periods():
            s = datetime.date(year, sm, sd)
            e = datetime.date(year, em, ed)
            if s <= e:
                if s <= today <= e:
                    return ((sm, sd), (em, ed))
            else:
                # 跨年區間：active 若 today >= s(今年) 或 today <= e(今年)
                if today >= s or today <= e:
                    return ((sm, sd), (em, ed))
        return None

    @staticmethod
    def is_tracking_enabled() -> bool:
        """回傳是否已設定至少一組選課期間"""
        return bool(Settings.get_tracking_periods())

    @staticmethod
    def validate() -> bool:
        """
        驗證配置是否完整

        Returns:
            True 如果配置有效，否則 False
        """
        if not Settings.TOKEN:
            print("❌ 錯誤：未設定 Discord Bot TOKEN")
            return False
        return True


def debug_print(*args, **kwargs) -> None:
    """
    除錯輸出函數（僅在 DEBUG=True 時輸出）

    Args:
        *args: 要輸出的內容
        **kwargs: print 函數的關鍵字參數
    """
    if Settings.DEBUG:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [DEBUG]", *args, **kwargs)
