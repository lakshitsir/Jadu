import os
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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

TMP = "temp"
os.makedirs(TMP, exist_ok=True)

pending_files = {}
queue = asyncio.Queue()
processing = False

# -------------------------
# UI TEXTS (YOUR ORIGINAL – UNCHANGED)
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
# SEXY AESTHETIC PROGRESS BAR
# -------------------------

def progress_bar(percent):
    filled = int(percent // 5)
    empty = 20 - filled
    return "▰" * filled + "▱" * empty


async def get_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    out = await proc.stdout.read()
    return float(out.decode().strip())


# -------------------------
# FFMPEG COMPRESS + LIVE PROGRESS
# -------------------------

async def compress_video(input_path, output_path, quality, msg):

    crf = {"high": "24", "medium": "28", "low": "32"}[quality]
    total_dur = await get_duration(input_path)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vcodec", "libx265",
        "-crf", crf,
        "-preset", "veryfast",
        "-acodec", "aac",
        "-b:a", "96k",
        "-progress", "pipe:1",
        output_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        line = line.decode(errors="ignore")

        if "out_time_ms" in line:
            ms = int(line.replace("out_time_ms=", ""))
            sec = ms / 1_000_000
            percent = (sec / total_dur) * 100

            bar = progress_bar(percent)

            await msg.edit(
                f"⚙️ **Compressing… {percent:.1f}%**\n"
                f"`{bar}`"
            )

    await proc.wait()


# -------------------------
# QUEUE WORKER
# -------------------------

async def worker():
    global processing

    while True:
        user_id, message = await queue.get()
        processing = True

        data = pending_files[user_id]
        input_path = data["file"]
        quality = data["quality"]
        output_path = input_path + "_compressed.mp4"

        progress_msg = await message.reply("⚙️ **Starting compression…**")

        await compress_video(input_path, output_path, quality, progress_msg)

        await progress_msg.edit("📤 **Uploading file…**")
        await message.reply_document(output_path, caption="🎥 **HQ Compressed File Ready!**")

        del pending_files[user_id]
        queue.task_done()

        if queue.empty():
            processing = False


# -------------------------
# HANDLERS (ORIGINAL + NEW FEATURES)
# -------------------------

@app.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(START_TEXT, reply_markup=START_BUTTONS)


@app.on_callback_query(filters.regex("compress_now"))
async def comp_now(_, q):
    await q.message.edit("🚀 **Send your video now to compress!**")


@app.on_callback_query(filters.regex("modes"))
async def modes(_, q):
    await q.message.edit(MODES_TEXT)


# -------------------------
# FILE RECEIVED → QUALITY OPTIONS
# -------------------------

@app.on_message(filters.video | filters.document)
async def handle_file(_, m):

    dl = await m.reply("📥 **Downloading your file…**")
    file_path = await m.download(file_name=TMP)
    await dl.delete()

    pending_files[m.from_user.id] = {"file": file_path}

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔹 High Quality", callback_data="q_high")],
        [InlineKeyboardButton("🔸 Medium Quality", callback_data="q_medium")],
        [InlineKeyboardButton("⚡ Low Quality", callback_data="q_low")],
    ])

    await m.reply(
        "🎚 **Select Compression Quality:**",
        reply_markup=buttons
    )


# -------------------------
# QUALITY SELECTED → ADD TO QUEUE
# -------------------------

@app.on_callback_query(filters.regex("q_"))
async def selected_quality(_, q):
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
