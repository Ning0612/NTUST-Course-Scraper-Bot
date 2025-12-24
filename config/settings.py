"""
Configuration settings for NTUST Course Scraper Bot.

This module centralizes environment variable access and provides
default values for all configuration options.
"""

import os
import datetime
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
