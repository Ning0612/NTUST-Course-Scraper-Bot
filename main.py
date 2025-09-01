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
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [DEBUG]", *args, **kwargs)

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

def extract_max_students_from_remark(text):
    """從備註文字提取人數上限（備用方法）"""
    if not text:
        return None
    
    patterns = [
        r'限制(\d+)人',
        r'限(\d+)人',
        r'上限(\d+)人',
        r'最多(\d+)人',
        r'(\d{2,3})人',  # 兩到三位數字後跟"人"
        r'／限(\d+)人',  # 特殊格式 "／限40人"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            number = int(match)
            if 5 <= number <= 200:  # 合理性檢查
                return number
    return None

async def get_max_students_improved(page):
    """
    改進的 max_students 提取函數
    優先使用點擊 more_horiz 按鈕獲取詳細資訊
    如果失敗則回退到備註欄提取
    """
    
    # 方法1：點擊 more_horiz 按鈕獲取詳細資訊
    try:
        debug_print("嘗試點擊 more_horiz 按鈕獲取詳細資訊...")
        
        # 點擊 more_horiz 按鈕
        clicked = await page.evaluate("""() => {
            let icons = document.querySelectorAll('i.material-icons');
            for (let icon of icons) {
                if (icon.textContent && icon.textContent.trim() === 'more_horiz') {
                    icon.click();
                    return true;
                }
            }
            return false;
        }""")
        
        if clicked:
            # 等待詳細資訊載入
            await asyncio.sleep(5)
            
            # 提取詳細資訊中的人數上限
            max_students = await page.evaluate("""() => {
                let allElements = document.querySelectorAll('*');
                
                for (let element of allElements) {
                    if (element.innerText) {
                        let text = element.innerText;
                        
                        // 優先尋找"加退選人數上限"
                        let match = text.match(/本校加退選人數上限[^：]*：\\s*(\\d+)/);
                        if (match) {
                            return parseInt(match[1]);
                        }
                        
                        // 其他可能的模式
                        let patterns = [
                            /加退選人數上限[^：]*：\\s*(\\d+)/,
                            /選課人數上限[^：]*：\\s*(\\d+)/,
                            /人數上限[^：]*：\\s*(\\d+)/,
                            /上限[^：]*：\\s*(\\d+)/
                        ];
                        
                        for (let pattern of patterns) {
                            let m = text.match(pattern);
                            if (m) {
                                let num = parseInt(m[1]);
                                if (num >= 5 && num <= 200) {
                                    return num;
                                }
                            }
                        }
                    }
                }
                return null;
            }""")
            
            if max_students:
                debug_print(f"✅ 從詳細資訊提取 max_students: {max_students}")
                return max_students
    
    except Exception as e:
        debug_print(f"點擊方法失敗: {e}")
    
    # 方法2：回退到備註欄提取
    try:
        debug_print("回退到備註欄提取方法...")
        
        remark_text = await page.evaluate("""() => {
            let table = document.querySelector(".v-datatable");
            if (!table) return null;
            let row = table.querySelector("tbody tr");
            if (!row) return null;
            let cols = row.querySelectorAll("td");
            if (cols.length <= 10) return null;
            return cols[10].innerText.trim();
        }""")
        
        if remark_text:
            max_from_remark = extract_max_students_from_remark(remark_text)
            if max_from_remark:
                debug_print(f"✅ 從備註欄提取 max_students: {max_from_remark}")
                return max_from_remark
    
    except Exception as e:
        debug_print(f"備註欄提取失敗: {e}")
    
    debug_print("❌ 無法提取 max_students")
    return None

def extract_enrolled_students(text):
    numbers = re.findall(r'\d+', text)
    return int(numbers[1]) if len(numbers) > 1 else None

async def fetch_course_info(guild_id, course_code, page):
    debug_print(f"🔄 開始持續追蹤課程 {course_code}")
    try:
        # Initial page load and search
        await page.goto("https://querycourse.ntust.edu.tw/querycourse/#/")
        await page.wait_for_load_state("networkidle", timeout=30000) # Longer timeout for initial load
        await asyncio.sleep(3) # Wait for page scripts to settle
        await page.fill("input[type='text']", course_code)
        await page.press("input[type='text']", "Enter")
        await page.wait_for_selector(".v-datatable", timeout=30000)
        await asyncio.sleep(3) # Wait for page scripts to settle
    except Exception as e:
        debug_print(f"❌ 追蹤任務初始化失敗 {course_code}: {e}")
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
                debug_print(f"⚠️ 追蹤中，未找到課程 {course_code}，將重試")
            else:
                course = result[0]
                enrolled_students = extract_enrolled_students(course["enrollment_text"])
                max_students = tracked_courses[guild_id][course_code]["max_students"]
                debug_print(f"📌 追蹤中，取得課程資訊: {course['course_name']} ({enrolled_students}/{max_students})")

                async with lock:
                    if guild_id not in tracked_courses or course_code not in tracked_courses[guild_id]:
                        debug_print(f"📌 課程 {course_code} 已不再追蹤，終止查詢任務")
                        break

                    tracked_courses[guild_id][course_code].update({
                        "name": course["course_name"],
                        "teacher": course["teacher_name"],
                        "lesson_time": course["lesson_time"],
                        "classroom": course["classroom"],
                        "remark": course["remark_text"],
                        "enrolled_students": enrolled_students,
                    })

                    if enrolled_students is not None and max_students is not None:
                        if enrolled_students < max_students:
                            if not tracked_courses[guild_id][course_code]["notified"]:
                                debug_print(f"✅ {course_code} 有名額，發送通知")
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
                                    debug_print(f"📤 發送課程名額通知到頻道 #{channel.name} ({channel.id}): {course['course_code']} {course['course_name']} ({enrolled_students}/{max_students})")
                                    await channel.send(message)
                        else:
                            tracked_courses[guild_id][course_code]["notified"] = False

        except asyncio.CancelledError:
            debug_print(f"⏹️ 任務 {course_code} 已被取消")
            break
        except Exception as e:
            debug_print(f"❌ 查詢課程 {course_code} 時發生錯誤：{type(e).__name__}: {e}")
        
        await asyncio.sleep(30)


@bot.event
async def on_ready():
    debug_print(f"✅ Bot 已啟動：{bot.user}")
    global playwright_browser, playwright_context
    playwright = await async_playwright().start()
    playwright_browser = await playwright.chromium.launch(headless=False)
    playwright_context = await playwright_browser.new_context()
    await bot.tree.sync()

    async with lock:
        for guild_id, courses in tracked_courses.items():
            for course_code, data in courses.items():
                try:
                    debug_print(f"🔄 初始化追蹤課程：{course_code} (伺服器ID: {guild_id})")
                    page = await playwright_context.new_page()
                    # 給每個頁面一個延遲，避免同時創建太多頁面
                    await asyncio.sleep(2)
                    task = asyncio.create_task(fetch_course_info(guild_id, course_code, page))
                    tracked_courses[guild_id][course_code]["page"] = page
                    tracked_courses[guild_id][course_code]["task"] = task
                    debug_print(f"✅ 成功創建追蹤任務：{course_code}")
                except Exception as e:
                    debug_print(f"❌ 初始化追蹤課程失敗 {course_code}: {e}")
                    # 如果初始化失敗，從追蹤列表中移除
                    if course_code in tracked_courses[guild_id]:
                        del tracked_courses[guild_id][course_code]
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
                        debug_print(f"📤 發送定期提醒通知到頻道 #{channel.name} ({channel.id}): {course_code} {data['name']}")
                        await channel.send(message)

@bot.tree.command(name="add", description="追蹤指定課程")
async def add(interaction: discord.Interaction, course_code: str):
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    
    debug_print(f"📩 收到追蹤課程請求: {interaction.user.name} ({user_id}) @ {interaction.guild.name} ({guild_id}) - {course_code}")
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
        debug_print(f"🔍 正在驗證課程 {course_code}")
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
        debug_print(f"❌ 驗證課程 {course_code} 時發生錯誤: {e}")
    finally:
        await validation_page.close()

    if details is None:
        debug_print(f"📤 通知使用者 {interaction.user.name} ({user_id}) 找不到課程 {course_code}")
        await interaction.followup.send(f"⚠️ **找不到課程 `{course_code}`！**\n請檢查課程代碼是否正確，或稍後再試。", ephemeral=True)
        return

    # Course found, add it to tracking - 使用改進的上限提取方法
    enrolled = extract_enrolled_students(details["enrollment_text"])
    
    # 重新打開頁面來提取準確的上限資訊
    max_page = await playwright_context.new_page()
    try:
        await max_page.goto("https://querycourse.ntust.edu.tw/querycourse/#/")
        await max_page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(3)
        await max_page.fill("input[type='text']", course_code)
        await max_page.press("input[type='text']", "Enter")
        await max_page.wait_for_selector(".v-datatable", timeout=30000)
        await asyncio.sleep(3)
        
        maximum = await get_max_students_improved(max_page)
        debug_print(f"🎯 初始化課程 {course_code} 獲取到上限: {maximum}")
    except Exception as e:
        debug_print(f"❌ 獲取課程上限失敗，使用備用方法: {e}")
        maximum = extract_max_students(details["remark_text"])
    finally:
        await max_page.close()
    
    async with lock:
        try:
            page = await playwright_context.new_page()
            await asyncio.sleep(1)  # 小延遲避免資源衝突
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
            debug_print(f"✅ 成功創建新的追蹤任務：{course_code}")
        except Exception as e:
            debug_print(f"❌ 創建追蹤任務失敗 {course_code}: {e}")
            await interaction.followup.send(f"⚠️ 創建追蹤任務時發生錯誤，請稍後重試。", ephemeral=True)
            return

    debug_print(f"📤 通知使用者 {interaction.user.name} ({user_id}) 已成功開始追蹤課程 {details['course_code']} - {details['course_name']}")
    await interaction.followup.send(f"✅ 已成功找到並開始追蹤課程：\n**`{details['course_code']} - {details['course_name']}`**")



@bot.tree.command(name="del", description="取消追蹤課程")
async def delete_course(interaction: discord.Interaction, course_code: str):
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    
    debug_print(f"📩 收到取消追蹤請求: {interaction.user.name} ({user_id}) @ {interaction.guild.name} ({guild_id}) - {course_code}")
    async with lock:
        if guild_id in tracked_courses and course_code in tracked_courses[guild_id]:
            tracked_courses[guild_id][course_code]["followers"].discard(user_id)
            if not tracked_courses[guild_id][course_code]["followers"]:
                await tracked_courses[guild_id][course_code]["page"].close()
                tracked_courses[guild_id][course_code]["task"].cancel()
                del tracked_courses[guild_id][course_code]
            save_data()
            debug_print(f"📤 通知使用者 {interaction.user.name} ({user_id}) 已取消追蹤課程 {course_code}")
            await interaction.response.send_message(f"✅ 你已取消追蹤 `{course_code}`")
        else:
            debug_print(f"📤 通知使用者 {interaction.user.name} ({user_id}) 嘗試取消未追蹤的課程 {course_code}")
            await interaction.response.send_message(f"⚠️ 你未追蹤 `{course_code}`！")

@bot.tree.command(name="set_channel", description="設定通知頻道")
async def set_channel(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    debug_print(f"📩 收到設定通知頻道請求: {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({guild_id}) - #{interaction.channel.name} ({interaction.channel.id})")
    guild_channels[guild_id] = interaction.channel.id
    save_data()
    debug_print(f"📤 通知使用者 {interaction.user.name} ({interaction.user.id}) 已設定通知頻道為 #{interaction.channel.name} ({interaction.channel.id})")
    await interaction.response.send_message(f"✅ 此頻道已設定為通知頻道！")

@bot.tree.command(name="help", description="顯示所有指令的說明")
async def help_command(interaction: discord.Interaction):
    debug_print(f"📩 收到說明指令請求: {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({interaction.guild.id})")
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
    debug_print(f"📤 向使用者 {interaction.user.name} ({interaction.user.id}) 發送說明訊息")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="list", description="列出此伺服器追蹤中的課程")
async def list_courses(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    
    debug_print(f"📩 收到課程列表請求: {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({guild_id})")
    async with lock:
        courses_copy = tracked_courses.get(guild_id, {}).copy()
    if not courses_copy:
        debug_print(f"📤 通知使用者 {interaction.user.name} ({interaction.user.id}) 該伺服器無追蹤中的課程")
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

    debug_print(f"📤 向使用者 {interaction.user.name} ({interaction.user.id}) 發送課程列表 ({len(message_chunks)} 個訊息)")
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
