import discord
from discord.ext import commands, tasks
import asyncio
import re
from dotenv import load_dotenv
import datetime
import json
import os
from playwright.async_api import async_playwright

# 讀取 Token
load_dotenv()
TOKEN = os.getenv("TOKEN")
DATA_FILE = "courses.json"

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

def debug_print(*args, **kwargs):
    if DEBUG:
        print(datetime.datetime.now(), *args, **kwargs)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

tracked_courses = {}
guild_channels = {}
lock = asyncio.Lock()
playwright_browser = None
playwright_context = None

# === JSON 儲存與載入 ===
def load_data():
    global tracked_courses, guild_channels
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 將 followers 轉為 set
            for gid in data["tracked_courses"]:
                for code in data["tracked_courses"][gid]:
                    data["tracked_courses"][gid][code]["followers"] = set(data["tracked_courses"][gid][code]["followers"])
            tracked_courses = {int(k): v for k, v in data["tracked_courses"].items()}
            guild_channels = {int(k): v for k, v in data["guild_channels"].items()}

def save_data():
    save_courses = {
        gid: {
            code: {
                **{k: v for k, v in info.items() if k not in ("page", "task")},
                "followers": list(info["followers"])
            } for code, info in courses.items()
        } for gid, courses in tracked_courses.items()
    }
    data = {
        "tracked_courses": save_courses,
        "guild_channels": guild_channels
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_max_students(text):
    match = re.search(r'限(\d+)人', text)
    return int(match.group(1)) if match else None

def extract_enrolled_students(text):
    numbers = re.findall(r'\d+', text)
    return int(numbers[1]) if len(numbers) > 1 else None

async def fetch_course_info(guild_id, course_code, page):
    debug_print(f"[DEBUG] 開始持續追蹤課程 {course_code} ...")
    try:
        # Initial page load and search
        await page.goto("https://querycourse.ntust.edu.tw/querycourse/#/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2) # Wait for page scripts to settle
        await page.fill("input[type='text']", course_code)
    except playwright.async_api.TimeoutError as e:
        debug_print(f"❌ [DEBUG] 追蹤任務初始化失敗 {course_code}: {e}")
        # Optionally, notify user about failure to track
        return # End this task

    while True:
        try:
            await page.press("input[type='text']", "Enter")
            await page.wait_for_selector(".v-datatable", timeout=15000)

            result = await page.evaluate("""() => {
                let table = document.querySelector(".v-datatable");
                if (!table) return [];
                let rows = table.querySelectorAll("tbody tr");
                let data = [];
                rows.forEach(row => {
                    let cols = row.querySelectorAll("td");
                    if (cols.length > 10) {
                        data.push({
                            course_code: cols[0].innerText.trim(),
                            course_name: cols[2].innerText.trim(),
                            teacher_name: cols[6].innerText.trim(),
                            enrollment_text: cols[7].innerText.trim(),
                            lesson_time: cols[8].innerText.trim(),
                            classroom: cols[9].innerText.trim(),
                            remark_text: cols[10].innerText.trim()
                        });
                    }
                });
                return data;
            }""")

            if not result:
                debug_print(f"⚠️ [DEBUG] 追蹤中，未找到課程 {course_code}，將重試...")
            else:
                course = result[0]
                enrolled_students = extract_enrolled_students(course["enrollment_text"])
                max_students = extract_max_students(course["remark_text"])
                debug_print(f"📌 [DEBUG] 追蹤中，取得課程資訊: {course['course_name']} ({enrolled_students}/{max_students})")

                async with lock:
                    if guild_id not in tracked_courses or course_code not in tracked_courses[guild_id]:
                        debug_print(f"📌 [DEBUG] 課程 {course_code} 已不再追蹤，終止查詢任務")
                        break

                    tracked_courses[guild_id][course_code].update({
                        "name": course["course_name"],
                        "teacher": course["teacher_name"],
                        "lesson_time": course["lesson_time"],
                        "classroom": course["classroom"],
                        "remark": course["remark_text"],
                        "enrolled_students": enrolled_students,
                        "max_students": max_students
                    })

                    if enrolled_students is not None and max_students is not None:
                        if enrolled_students < max_students:
                            if not tracked_courses[guild_id][course_code]["notified"]:
                                debug_print(f"✅ [DEBUG] {course_code} 有名額，發送通知！")
                                tracked_courses[guild_id][course_code]["notified"] = True
                                channel = bot.get_channel(guild_channels.get(guild_id))
                                if channel:
                                    followers = " ".join(f"<@{user_id}>" for user_id in tracked_courses[guild_id][course_code]["followers"])
                                    message = (
                                        f"{followers} 🎉 **{course['course_code']} {course['course_name']}** 有名額！\n"
                                        f"👨‍🏫 **授課教師:** {course['teacher_name']}\n"
                                        f"🕒 **時間:** {course['lesson_time']}\n"
                                        f"📍 **教室:** {course['classroom']}\n"
                                        f"📌 **目前人數:** {enrolled_students}/{max_students}\n"
                                        f"🔗 [前往選課](https://courseselection.ntust.edu.tw/AddAndSub/B01/B01)"
                                    )
                                    await channel.send(message)
                        else:
                            tracked_courses[guild_id][course_code]["notified"] = False

        except asyncio.CancelledError:
            debug_print(f"[DEBUG] 任務 {course_code} 已被取消")
            break
        except playwright.async_api.TimeoutError:
            debug_print(f"❌ [DEBUG] 查詢課程 {course_code} 時發生超時錯誤，將重試...")
        except Exception as e:
            debug_print(f"❌ [DEBUG] 查詢課程 {course_code} 時發生未預期錯誤：{type(e).__name__}: {e}")
        
        await asyncio.sleep(30)


@bot.event
async def on_ready():
    debug_print(f"✅ [DEBUG] Bot 已啟動：{bot.user}")
    global playwright_browser, playwright_context
    playwright = await async_playwright().start()
    playwright_browser = await playwright.chromium.launch(headless=True)
    playwright_context = await playwright_browser.new_context()
    await bot.tree.sync()

    async with lock:
        for guild_id, courses in tracked_courses.items():
            for course_code, data in courses.items():
                debug_print(f"🔄 [DEBUG] 初始化追蹤課程：{course_code} ({guild_id})")
                page = await playwright_context.new_page()
                task = asyncio.create_task(fetch_course_info(guild_id, course_code, page))
                tracked_courses[guild_id][course_code]["page"] = page
                tracked_courses[guild_id][course_code]["task"] = task
            await asyncio.sleep(1)

    if not periodic_notify.is_running():
        periodic_notify.start()

@tasks.loop(minutes=1)
async def periodic_notify():
    async with lock:
        for guild_id, courses in tracked_courses.items():
            channel_id = guild_channels.get(guild_id)
            channel = bot.get_channel(channel_id) if channel_id else None
            if channel:
                for course_code, data in courses.items():
                    if data["notified"]:
                        followers = " ".join(f"<@{user_id}>" for user_id in data["followers"])
                        message = (
                            f"{followers} 📢 **`{course_code} {data['name']}`** 仍有名額！\n"
                            f"🔗 [前往選課](https://courseselection.ntust.edu.tw/AddAndSub/B01/B01)"
                        )
                        await channel.send(message)

@bot.tree.command(name="add", description="追蹤指定課程")
async def add(interaction: discord.Interaction, course_code: str):
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    
    await interaction.response.defer()

    async with lock:
        if guild_id not in tracked_courses:
            tracked_courses[guild_id] = {}

        if course_code in tracked_courses[guild_id]:
            tracked_courses[guild_id][course_code]["followers"].add(user_id)
            save_data()
            await interaction.followup.send(f"✅ 已將您加入 `{course_code}` 的追蹤列表。", ephemeral=True)
            return

    # Validate the course code with a temporary page
    validation_page = await playwright_context.new_page()
    details = None
    try:
        debug_print(f"🔍 [DEBUG] 正在驗證課程 {course_code} ...")
        await validation_page.goto("https://querycourse.ntust.edu.tw/querycourse/#/")
        await validation_page.wait_for_load_state("networkidle", timeout=30000) # Longer timeout for initial load
        await asyncio.sleep(3) # Wait for page scripts to settle
        await validation_page.fill("input[type='text']", course_code)
        await validation_page.press("input[type='text']", "Enter")
        await validation_page.wait_for_selector(".v-datatable", timeout=30000)
        await asyncio.sleep(3) # Wait for page scripts to settle
        details = await validation_page.evaluate("""() => {
            let table = document.querySelector(".v-datatable");
            if (!table) return null;
            let row = table.querySelector("tbody tr");
            if (!row) return null;
            let cols = row.querySelectorAll("td");
            if (cols.length <= 10) return null;
            return {
                course_code: cols[0].innerText.trim(),
                course_name: cols[2].innerText.trim(),
                teacher_name: cols[6].innerText.trim(),
                enrollment_text: cols[7].innerText.trim(),
                lesson_time: cols[8].innerText.trim(),
                classroom: cols[9].innerText.trim(),
                remark_text: cols[10].innerText.trim()
            };
        }""")
    except Exception as e:
        debug_print(f"❌ [DEBUG] 驗證課程 {course_code} 時發生錯誤: {e}")
    finally:
        await validation_page.close()

    if details is None:
        await interaction.followup.send(f"⚠️ **找不到課程 `{course_code}`！**\n請檢查課程代碼是否正確，或稍後再試。", ephemeral=True)
        return

    # Course found, add it to tracking
    enrolled = extract_enrolled_students(details["enrollment_text"])
    maximum = extract_max_students(details["remark_text"])
    
    async with lock:
        page = await playwright_context.new_page()
        task = asyncio.create_task(fetch_course_info(guild_id, course_code, page))
        tracked_courses[guild_id][course_code] = {
            "name": details["course_name"],
            "teacher": details["teacher_name"],
            "lesson_time": details["lesson_time"],
            "classroom": details["classroom"],
            "remark": details["remark_text"],
            "page": page,
            "task": task,
            "notified": False,
            "followers": {user_id},
            "enrolled_students": enrolled,
            "max_students": maximum
        }
        save_data()

    await interaction.followup.send(f"✅ 已成功找到並開始追蹤課程：\n**`{details['course_code']} - {details['course_name']}`**", ephemeral=True)



@bot.tree.command(name="del", description="取消追蹤課程")
async def delete_course(interaction: discord.Interaction, course_code: str):
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    async with lock:
        if guild_id in tracked_courses and course_code in tracked_courses[guild_id]:
            tracked_courses[guild_id][course_code]["followers"].discard(user_id)
            if not tracked_courses[guild_id][course_code]["followers"]:
                await tracked_courses[guild_id][course_code]["page"].close()
                tracked_courses[guild_id][course_code]["task"].cancel()
                del tracked_courses[guild_id][course_code]
            save_data()
            await interaction.response.send_message(f"✅ 你已取消追蹤 `{course_code}`")
        else:
            await interaction.response.send_message(f"⚠️ 你未追蹤 `{course_code}`！")

@bot.tree.command(name="set_channel", description="設定通知頻道")
async def set_channel(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    guild_channels[guild_id] = interaction.channel.id
    save_data()
    await interaction.response.send_message(f"✅ 此頻道已設定為通知頻道！")

@bot.tree.command(name="help", description="顯示所有指令的說明")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 機器人指令說明",
        description="以下是所有可用的斜線指令：",
        color=discord.Color.blue()
    )
    embed.add_field(name="`/add <course_code>`", value="開始追蹤一個新的課程。", inline=False)
    embed.add_field(name="`/del <course_code>`", value="取消追蹤一個指定的課程。", inline=False)
    embed.add_field(name="`/list`", value="列出此伺服器上所有正在追蹤的課程。", inline=False)
    embed.add_field(name="`/set_channel`", value="將目前的頻道設為接收通知的頻道。", inline=False)
    embed.add_field(name="`/help`", value="顯示這則說明訊息。", inline=False)
    embed.set_footer(text="NTUST Course Scraper Bot")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="list", description="列出此伺服器追蹤中的課程")
async def list_courses(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    async with lock:
        courses_copy = tracked_courses.get(guild_id, {}).copy()
    if not courses_copy:
        await interaction.response.send_message("⚠️ 目前此伺服器無追蹤中的課程！")
        return

    message_list = []
    for code, data in courses_copy.items():
        followers_list = [await bot.fetch_user(user_id) for user_id in data["followers"]]
        followers = ", ".join(user.name for user in followers_list) or "無人追蹤"
        message_list.append(
            f"📌 `{code}` - {data['name']}\n"
            f"👨‍🏫 **教師:** {data['teacher']}\n"
            f"🕒 **時間:** {data['lesson_time']}\n"
            f"📍 **教室:** {data['classroom']}\n"
            f"📌 **目前人數:** {data['enrolled_students']}/{data['max_students']}\n"
            f"👥 **追蹤者:** {followers}\n"
            f"🔹🔹🔹🔹🔹"
        )

    message_chunks = []
    current_chunk = ""
    for line in message_list:
        if len(current_chunk) + len(line) + 1 > 2000:
            message_chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += line + "\n"
    if current_chunk:
        message_chunks.append(current_chunk)

    for i, msg in enumerate(message_chunks):
        if i == 0:
            await interaction.response.send_message(msg)
        else:
            await interaction.followup.send(msg)

async def shutdown():
    if playwright_browser:
        await playwright_browser.close()

async def main():
    load_data()
    try:
        await bot.start(TOKEN)
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
