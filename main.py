"""
NTUST Course Scraper Bot - Phase 2 Refactored Version

Main entry point for the Discord bot. This file has been refactored
to use a modular architecture with service layers.
"""

import discord
from discord.ext import commands, tasks
import asyncio

# 配置與設定
from config.settings import Settings, debug_print

# 服務層
from services.worker_pool import WorkerPool
from services.data_manager import DataManager
from services.tracker import CourseTracker
from services.api_client import init_api_client

# Bot 指令
from bot.commands import setup_commands


# Discord Bot 初始化
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化服務
data_manager = DataManager(Settings.DATA_FILE)
worker_pool = WorkerPool(size=Settings.WORKER_POOL_SIZE)
tracker = CourseTracker(bot, data_manager.guild_channels, worker_pool, debug_print)


@bot.event
async def on_ready():
    """Bot 啟動事件"""
    debug_print(f"✅ Bot 已啟動：{bot.user}")

    # 初始化 API Client
    init_api_client()
    debug_print("✅ Course API Client 已初始化")

    # 啟動 Worker Pool
    await worker_pool.start()
    debug_print(f"✅ Worker Pool 已啟動 (大小: {Settings.WORKER_POOL_SIZE})")

    # 同步斜線指令
    await bot.tree.sync()
    debug_print("✅ 斜線指令已同步")

    # 恢復追蹤狀態
    await data_manager.restore_tracking(tracker)

    # 啟動輪詢任務
    await tracker.start_polling(interval=Settings.POLLING_INTERVAL)

    # 啟動定期通知任務
    if not periodic_notify.is_running():
        periodic_notify.start()
        debug_print(f"✅ 定期通知任務已啟動 (間隔: {Settings.NOTIFICATION_INTERVAL} 分鐘)")


@tasks.loop(minutes=Settings.NOTIFICATION_INTERVAL)
async def periodic_notify():
    """
    定期通知任務

    每隔一段時間檢查所有有空位且已通知的課程，
    持續提醒追蹤者。
    """
    try:
        async with tracker.lock:
            for guild_id, courses in tracker.tracked_courses.items():
                for course_code, course in courses.items():
                    # 如果課程有空位且已發送通知，持續提醒
                    if course.has_available_seats() and course.notified:
                        channel_id = data_manager.get_guild_channel(guild_id)
                        if not channel_id:
                            continue

                        channel = bot.get_channel(channel_id)
                        if not channel:
                            continue

                        followers = " ".join(f"<@{user_id}>" for user_id in course.followers)
                        message = (
                            f"{followers} 📢 **{course.code} {course.name}** 仍有名額！\n"
                            f"📌 **目前人數:** {course.enrolled_students}/{course.max_students}\n"
                            f"🔗 [前往選課](https://courseselection.ntust.edu.tw/AddAndSub/B01/B01)"
                        )

                        await channel.send(message)
                        debug_print(f"📢 定期提醒: {course.code} 仍有名額")

    except Exception as e:
        debug_print(f"❌ 定期通知任務錯誤: {e}")


@periodic_notify.before_loop
async def before_periodic_notify():
    """等待 Bot 完全啟動"""
    await bot.wait_until_ready()


async def shutdown():
    """清理資源"""
    debug_print("🛑 開始清理資源...")

    # 停止輪詢任務
    await tracker.stop_polling()

    # 停止 Worker Pool
    await worker_pool.stop()

    debug_print("✅ 清理完成")


async def main():
    """主程式進入點"""
    # 驗證配置
    if not Settings.validate():
        return

    # 註冊指令
    setup_commands(bot, tracker, data_manager)
    debug_print("✅ Discord 指令已註冊")

    try:
        # 啟動 Bot
        await bot.start(Settings.TOKEN)
    finally:
        # 清理資源
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
