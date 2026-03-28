"""
Configuration settings for NTUST Course Scraper Bot.

This module centralizes environment variable access and provides
default values for all configuration options.
"""

import os
import datetime
from typing import List, Tuple
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()


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

    # 定期清除追蹤課程日期（格式：01-15,07-01,09-15）
    _CLEANUP_DATES_STR: str = os.getenv("CLEANUP_DATES", "")

    @staticmethod
    def get_cleanup_dates() -> List[Tuple[int, int]]:
        """
        解析清除日期設定

        Returns:
            List of (month, day) tuples
            例如：[(1, 15), (7, 1), (9, 15)]
        """
        if not Settings._CLEANUP_DATES_STR.strip():
            return []

        cleanup_dates = []
        for date_str in Settings._CLEANUP_DATES_STR.split(","):
            date_str = date_str.strip()
            if not date_str:
                continue

            try:
                # 解析格式：MM-DD
                parts = date_str.split("-")
                if len(parts) != 2:
                    print(f"⚠️ 警告：無效的清除日期格式 '{date_str}'（應為 MM-DD），已略過")
                    continue

                month = int(parts[0])
                day = int(parts[1])

                # 用 datetime.date 驗證日期合法性（使用非閏年，避免 02-29 誤判）
                datetime.date(2001, month, day)

                cleanup_dates.append((month, day))

            except ValueError:
                print(f"⚠️ 警告：無效的清除日期 '{date_str}'，已略過")
                continue

        return cleanup_dates

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
