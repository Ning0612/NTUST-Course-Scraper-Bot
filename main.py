"""
NTUST Course Tracker Bot - Phase 2 Refactored Version

Main entry point for the Discord bot. This file has been refactored
to use a modular architecture with service layers.
"""

import discord
from discord.ext import commands, tasks
import asyncio
import datetime

# 配置與設定
from config.settings import Settings, TAIPEI_TZ as _TAIPEI_TZ, debug_print

# 服務層
from services.worker_pool import WorkerPool
from services.data_manager import DataManager
from services.tracker import CourseTracker, find_writable_channel
from services.api_client import init_api_client

# Bot 指令
from bot.commands import setup_commands


# 記錄上次已知的 active period key，用於偵測轉場（避免重複觸發）
# 格式："MM-DD~MM-DD" 或 "" (不在任何 active period)
_last_active_period_key: str = ""


def _period_key(period) -> str:
    """將 period tuple 轉為字串 key，方便跨天比對"""
    if period is None:
        return ""
    (sm, sd), (em, ed) = period
    return f"{sm:02d}-{sd:02d}~{em:02d}-{ed:02d}"

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
    global _last_active_period_key
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

    # 判斷目前選課期間狀態並初始化 _last_active_period_key
    today = datetime.datetime.now(_TAIPEI_TZ).date()
    active = Settings.get_active_period(today)
    _last_active_period_key = _period_key(active)

    if not Settings.is_tracking_enabled():
        # 未設定 TRACKING_PERIODS：維持舊行為（永遠輪詢）
        await tracker.start_polling(interval=Settings.POLLING_INTERVAL)
        debug_print("⚠️ 未設定 TRACKING_PERIODS，維持永遠輪詢模式")
    elif active:
        # 目前為選課期間，啟動輪詢
        await tracker.start_polling(interval=Settings.POLLING_INTERVAL)
        debug_print(f"🟢 目前為選課期間 {_last_active_period_key}，啟動課程輪詢")
    else:
        debug_print("⏸️ 目前非選課期間，不啟動課程輪詢")

    # 啟動定期通知任務
    if not periodic_notify.is_running():
        periodic_notify.start()
        debug_print(f"✅ 定期通知任務已啟動 (間隔: {Settings.NOTIFICATION_INTERVAL} 分鐘)")

    # 啟動選課期間檢查任務
    if Settings.is_tracking_enabled() and not check_date_range.is_running():
        check_date_range.start()
        periods = Settings.get_tracking_periods()
        periods_str = ", ".join(
            f"{sm:02d}-{sd:02d}~{em:02d}-{ed:02d}"
            for (sm, sd), (em, ed) in periods
        )
        debug_print(f"✅ 選課期間檢查任務已啟動 (期間: {periods_str})")


@tasks.loop(minutes=Settings.NOTIFICATION_INTERVAL)
async def periodic_notify():
    """
    定期通知任務

    每隔一段時間檢查所有有空位且已通知的課程，
    持續提醒追蹤者。僅在選課期間（或未設定期間時）執行。
    """
    # 若已設定選課期間但目前非 active，靜默跳過
    if Settings.is_tracking_enabled():
        today = datetime.datetime.now(_TAIPEI_TZ).date()
        if not Settings.get_active_period(today):
            return

    try:
        # 取得需要通知的課程列表，縮小 lock 範圍以避免阻塞 I/O
        courses_by_guild = {}
        async with tracker.lock:
            for guild_id, courses in tracker.tracked_courses.items():
                courses_by_guild[guild_id] = list(courses.values())

        for guild_id, courses in courses_by_guild.items():
            try:
                channel_id = data_manager.get_guild_channel(guild_id)
                channel = bot.get_channel(channel_id) if channel_id else None

                if not channel:
                    debug_print(f"⚠️ 伺服器 {guild_id} 未設定通知頻道或頻道不存在")
                    
                    # 嘗試在其他有權限的頻道發送「未設定頻道」警告
                    if guild_id not in tracker.warned_guilds:
                        guild = bot.get_guild(guild_id)
                        if guild:
                            fallback_channel = find_writable_channel(guild, bot.user.id)
                            if fallback_channel:
                                warning_msg = (
                                    f"⚠️ **未設定通知頻道警告**\n"
                                    f"本伺服器尚未設定（或已刪除）選課通知頻道，導致無法發送定期課程提醒。\n"
                                    f"請管理員使用 `/set_channel` 指令在目標頻道中重新設定。"
                                )
                                try:
                                    await fallback_channel.send(warning_msg)
                                    tracker.warned_guilds.add(guild_id)
                                    debug_print(f"✅ 已在備用頻道 #{fallback_channel.name} 發送設定警告")
                                except Exception as e:
                                    debug_print(f"❌ 在備用頻道發送警告失敗: {e}")
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


@tasks.loop(minutes=10)
async def check_date_range():
    """
    定期檢查選課期間狀態並執行轉場動作

    每 10 分鐘執行一次，偵測是否進入或離開選課期間：
    - 非 active → active：啟動課程輪詢
    - active → 非 active：停止輪詢，清除追蹤課程，發送通知
    """
    global _last_active_period_key
    try:
        today = datetime.datetime.now(_TAIPEI_TZ).date()
        active = Settings.get_active_period(today)
        current_key = _period_key(active)

        # 無變化，不做任何事
        if current_key == _last_active_period_key:
            return

        was_active = bool(_last_active_period_key)
        now_active = bool(current_key)

        if now_active and not was_active:
            # 非 active → active：啟動輪詢（先執行再更新 state，失敗可重試）
            if tracker.polling_task is None:
                await tracker.start_polling(interval=Settings.POLLING_INTERVAL)
            _last_active_period_key = current_key
            debug_print(f"🟢 進入選課期間 {current_key}，啟動課程輪詢")

        elif now_active and was_active:
            # active → active：period 切換（相接期間），同步 key 即可
            _last_active_period_key = current_key
            debug_print(f"🔄 選課期間切換至 {current_key}")

        elif not now_active and was_active:
            # active → 非 active：停止輪詢 + 清除課程（成功後才更新 state）
            await tracker.stop_polling()

            guild_counts = await tracker.clear_all_courses()
            total_cleared = sum(guild_counts.values())

            if data_manager.save(tracker.tracked_courses):
                _last_active_period_key = ""  # 存檔成功才更新 state，失敗則下次重試
                debug_print(f"✅ 選課期間結束，已清除 {total_cleared} 門課程")
            else:
                debug_print("❌ 清除後存檔失敗，下次將重試")

            # 有課程被清除才發通知
            if total_cleared > 0:
                now_str = datetime.datetime.now(_TAIPEI_TZ).strftime('%Y-%m-%d')
                for guild_id, channel_id in data_manager.guild_channels.items():
                    channel = bot.get_channel(channel_id)
                    if channel:
                        try:
                            guild_count = guild_counts.get(guild_id, 0)
                            await channel.send(
                                f"📢 **自動清除通知**\n\n"
                                f"選課期間已結束，本伺服器的追蹤課程已於 {now_str} 自動清除。\n"
                                f"共清除 {guild_count} 門課程。\n\n"
                                f"請使用 `/add` 指令在下次選課開始時重新追蹤課程。"
                            )
                            debug_print(f"✅ 已通知伺服器 {guild_id} 選課期間結束")
                        except Exception as e:
                            debug_print(f"❌ 通知伺服器 {guild_id} 失敗: {e}")

    except Exception as e:
        debug_print(f"❌ 選課期間檢查任務錯誤: {e}")


@check_date_range.before_loop
async def before_check_date_range():
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
