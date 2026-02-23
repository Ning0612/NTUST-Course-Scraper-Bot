"""
NTUST Course Scraper Bot - Phase 2 Refactored Version

Main entry point for the Discord bot. This file has been refactored
to use a modular architecture with service layers.
"""

import discord
from discord.ext import commands, tasks
import asyncio
import datetime

# 配置與設定
from config.settings import Settings, debug_print

# 服務層
from services.worker_pool import WorkerPool
from services.data_manager import DataManager
from services.tracker import CourseTracker, find_writable_channel
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

    # 啟動定期清除檢查任務
    cleanup_dates = Settings.get_cleanup_dates()
    if cleanup_dates and not check_cleanup_dates.is_running():
        check_cleanup_dates.start()
        debug_print(
            f"✅ 定期清除檢查任務已啟動 "
            f"(清除日期: {', '.join(f'{m:02d}-{d:02d}' for m, d in cleanup_dates)})"
        )


@tasks.loop(minutes=Settings.NOTIFICATION_INTERVAL)
async def periodic_notify():
    """
    定期通知任務

    每隔一段時間檢查所有有空位且已通知的課程，
    持續提醒追蹤者。
    """
    try:
        # 取得需要通知的課程列表，縮小 lock 範圍以避免阻塞 I/O
        courses_by_guild = {}
        async with tracker.lock:
            for guild_id, courses in tracker.tracked_courses.items():
                courses_by_guild[guild_id] = list(courses.values())

        for guild_id, courses in courses_by_guild.items():
            try:
                channel_id = data_manager.get_guild_channel(guild_id)
                if not channel_id:
                    continue

                channel = bot.get_channel(channel_id)
                if not channel:
                    continue

                # 權限檢查 (使用較安全的方式取得自身成員對象)
                me = channel.guild.me or channel.guild.get_member(bot.user.id)
                if not me:
                    continue

                permissions = channel.permissions_for(me)
                if not permissions.send_messages:
                    debug_print(
                        f"❌ 權限不足: 伺服器 {guild_id} 的頻道 "
                        f"#{channel.name} ({channel_id}) 缺少發送訊息權限"
                    )

                    # 嘗試在其他有權限的頻道發送警告
                    if guild_id not in tracker.warned_guilds:
                        fallback_channel = find_writable_channel(channel.guild, bot.user.id)
                        if fallback_channel and fallback_channel.id != channel.id:
                            warning_msg = (
                                f"⚠️ **權限不足警告**\n"
                                f"Bot 目前在定期通知頻道 <#{channel.id}> 中缺少「發送訊息」權限，"
                                f"導致無法發送定期課程提醒。\n"
                                f"請管理員檢查頻道權限設定，或使用 `/set_channel` 重新設定頻道。"
                            )
                            try:
                                await fallback_channel.send(warning_msg)
                                tracker.warned_guilds.add(guild_id)
                                debug_print(f"✅ 已在備用頻道 #{fallback_channel.name} 發送權限警告")
                            except Exception as e:
                                debug_print(f"❌ 在備用頻道發送警告失敗: {e}")
                    continue

                # 權限正常，重置警告狀態
                if guild_id in tracker.warned_guilds:
                    tracker.warned_guilds.remove(guild_id)

                for course in courses:
                    # 如果課程有空位且已發送通知，持續提醒
                    if course.has_available_seats() and course.notified:
                        followers = " ".join(f"<@{user_id}>" for user_id in course.followers)
                        message = (
                            f"{followers} 📢 **{course.code} {course.name}** 仍有名額！\n"
                            f"📌 **目前人數:** {course.enrolled_students}/{course.max_students}\n"
                            f"🔗 [前往選課](https://courseselection.ntust.edu.tw/AddAndSub/B01/B01)"
                        )

                        await channel.send(message)
                        debug_print(f"📢 定期提醒: {course.code} 仍有名額")
            except discord.Forbidden:
                debug_print(f"❌ 權限錯誤 (403): 無法在伺服器 {guild_id} 的頻道發送訊息")
            except Exception as e:
                debug_print(f"❌ 定期通知伺服器 {guild_id} 時發生錯誤: {e}")

    except Exception as e:
        debug_print(f"❌ 定期通知任務全局錯誤: {e}")


@periodic_notify.before_loop
async def before_periodic_notify():
    """等待 Bot 完全啟動"""
    await bot.wait_until_ready()


@tasks.loop(hours=12)
async def check_cleanup_dates():
    """
    定期檢查是否到達清除日期

    每天執行一次，檢查當前日期是否在清除日期列表中。
    如果是，則清除所有追蹤課程並儲存資料。
    """
    try:
        cleanup_dates = Settings.get_cleanup_dates()
        if not cleanup_dates:
            return

        now = datetime.datetime.now()
        current_date = (now.month, now.day)

        # 檢查是否為清除日期
        if current_date in cleanup_dates:
            debug_print(
                f"📅 到達清除日期 {now.month:02d}-{now.day:02d}，開始清除所有追蹤課程..."
            )

            # 清除所有課程
            cleared_count = await tracker.clear_all_courses()

            # 儲存資料
            data_manager.save_data(tracker.tracked_courses)

            # 通知所有伺服器（如果有設定通知頻道）
            for guild_id, channel_id in data_manager.guild_channels.items():
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        message = (
                            f"📢 **自動清除通知**\n\n"
                            f"因應學期更新，所有追蹤課程已於 {now.strftime('%Y-%m-%d')} 自動清除。\n"
                            f"共清除 {cleared_count} 門課程。\n\n"
                            f"請使用 `/add` 指令重新追蹤本學期的課程。"
                        )
                        await channel.send(message)
                        debug_print(f"✅ 已通知伺服器 {guild_id} 清除課程")
                    except Exception as e:
                        debug_print(f"❌ 通知伺服器 {guild_id} 失敗: {e}")

            debug_print(f"✅ 清除任務完成，共清除 {cleared_count} 門課程")

    except Exception as e:
        debug_print(f"❌ 檢查清除日期任務錯誤: {e}")


@check_cleanup_dates.before_loop
async def before_check_cleanup_dates():
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
