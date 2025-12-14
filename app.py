import os
import asyncio
import subprocess
import time
import shutil
import uuid

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# -------------------------
# YOUR CREDENTIALS
# -------------------------

API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"

app = Client(
    "neon_compressor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

BASE_TMP = "temp"
os.makedirs(BASE_TMP, exist_ok=True)

pending_files = {}
queue = asyncio.Queue()
processing = False

# -------------------------
# UI TEXTS (UNCHANGED)
# -------------------------

START_TEXT = """\
🔮 𝗣𝗿𝗶𝘃𝗮𝘁𝗲 𝗛𝗤 𝗖𝗼𝗺𝗽𝗿𝗲𝘀𝘀𝗼𝗿 𝗦𝘆𝘀𝘁𝗲𝗺 ⚡

Welcome to the Neon Compression Engine.
Where heavy files transform into lightweight
versions — without losing their soul.

📥 Send any video/file to begin
⚙️ Engine Mode: HEVC • 90% Same Quality
🚀 Speed: Ultra Optimized
🛡️ Privacy: Your files stay private
📦 Output Size: Up to 10x Smaller

👨‍💻 Developer – @lakshitpatidar
"""

START_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔧 Start Compression", callback_data="compress_now")],
    [InlineKeyboardButton("📚 Compression Modes", callback_data="modes")],
    [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/lakshitpatidar")]
])

MODES_TEXT = """\
🎚 **Compression Modes Available**

🔹 **High Quality (Recommended)**
• 90% Same Quality
• 2GB → 200–400MB

🔹 **Medium Quality**
• 70–80% Quality

🔹 **Low Quality**
• 50–60% Quality

(Current mode = High Quality HEVC)
"""

# -------------------------
# PROGRESS BAR
# -------------------------

def progress_bar(percent):
    filled = int(percent // 5)
    empty = 20 - filled
    return "▰" * filled + "▱" * empty


async def get_duration(path):
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    out = await proc.stdout.read()
    return float(out.decode().strip())


# -------------------------
# COMPRESS (ANTI FREEZE)
# -------------------------

async def compress_video(input_path, output_path, quality, msg):

    crf = {"high": "24", "medium": "28", "low": "32"}[quality]
    total_dur = await get_duration(input_path)

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-i", input_path,
        "-vcodec", "libx265",
        "-crf", crf,
        "-preset", "veryfast",
        "-acodec", "aac",
        "-b:a", "96k",
        "-progress", "pipe:1",
        output_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    last_edit = 0

    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        if b"out_time_ms=" in line:
            now = time.time()
            if now - last_edit < 1.5:
                continue

            last_edit = now
            try:
                ms = int(line.decode().split("=")[1])
                percent = min((ms / 1_000_000) / total_dur * 100, 100)
                await msg.edit(
                    f"⚙️ **Compressing… {percent:.1f}%**\n"
                    f"`{progress_bar(percent)}`"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except:
                pass

    await proc.wait()


# -------------------------
# QUEUE WORKER (HARD SAFE)
# -------------------------

async def worker():
    global processing

    while True:
        user_id, message = await queue.get()
        processing = True

        data = pending_files[user_id]
        job_dir = data["dir"]
        input_path = data["input"]
        quality = data["quality"]
        output_path = os.path.join(job_dir, "compressed.mp4")

        try:
            progress = await message.reply("⚙️ **Starting compression…**")
            await compress_video(input_path, output_path, quality, progress)

            await progress.edit("📤 **Uploading file…**")
            await message.reply_document(
                output_path,
                caption="🎥 **HQ Compressed File Ready!**"
            )

        finally:
            # 🔥 HARD DELETE (NO TRACE LEFT)
            shutil.rmtree(job_dir, ignore_errors=True)
            pending_files.pop(user_id, None)
            queue.task_done()

            if queue.empty():
                processing = False


# -------------------------
# HANDLERS
# -------------------------

@app.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(START_TEXT, reply_markup=START_BUTTONS)


@app.on_message(filters.video | filters.document)
async def handle_file(_, m):

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(BASE_TMP, f"{m.from_user.id}_{job_id}")
    os.makedirs(job_dir, exist_ok=True)

    dl = await m.reply("📥 **Downloading your file…**")
    input_path = await m.download(file_name=job_dir)
    await dl.delete()

    pending_files[m.from_user.id] = {
        "input": input_path,
        "dir": job_dir
    }

    await m.reply(
        "🎚 **Select Compression Quality:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔹 High Quality", callback_data="q_high")],
            [InlineKeyboardButton("🔸 Medium Quality", callback_data="q_medium")],
            [InlineKeyboardButton("⚡ Low Quality", callback_data="q_low")]
        ])
    )


@app.on_callback_query(filters.regex("q_"))
async def select_quality(_, q):
    quality = q.data.replace("q_", "")
    pending_files[q.from_user.id]["quality"] = quality

    await q.message.edit(
        f"⏳ **Added to Queue**\n"
        f"Quality: `{quality}`\n"
        f"Waiting for your turn…"
    )

    await queue.put((q.from_user.id, q.message))

    global processing
    if not processing:
        asyncio.create_task(worker())


# -------------------------
# START BOT
# -------------------------

print("🔥 Neon Compressor Bot Started!")
app.run()
