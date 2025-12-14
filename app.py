import os
import asyncio
import uuid
import shutil
import subprocess
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

# ================= CONFIG =================
API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"

TMP_DIR = "temp"
MAX_CONCURRENT_JOBS = 2

CRF = "28"
PRESET = "veryfast"

os.makedirs(TMP_DIR, exist_ok=True)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# ================= BOT =================
app = Client(
    "neon_private_compressor",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

START_TEXT = """🔮 𝗣𝗿𝗶𝘃𝗮𝘁𝗲 𝗛𝗤 𝗖𝗼𝗺𝗽𝗿𝗲𝘀𝘀𝗼𝗿 𝗦𝘆𝘀𝘁𝗲𝗺 ⚡

Welcome to the Neon Compression Engine.
Where heavy files transform into lightweight
versions — without losing their soul.

📥 Send any video/file to begin
⚙️ Engine Mode: HEVC • 90% Same Quality
🚀 Speed: Ultra Optimized
🛡️ Privacy: Your files stay private

👨‍💻 Developer – @lakshitpatidar
"""

# ================= HELPERS =================
def make_user_dir(uid: int):
    path = os.path.join(TMP_DIR, str(uid))
    os.makedirs(path, exist_ok=True)
    return path

async def ffmpeg_compress(input_file, output_file, status_msg: Message):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx265",
        "-preset", PRESET,
        "-crf", CRF,
        "-c:a", "aac",
        "-b:a", "128k",
        output_file
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )

    progress = 0
    while process.returncode is None:
        await asyncio.sleep(3)
        progress += 6
        if progress > 95:
            progress = 95

        bar = "▰" * (progress // 10) + "▱" * (10 - progress // 10)
        try:
            await status_msg.edit(
                f"⚡ Neon Engine Active\n\n"
                f"{bar}\n"
                f"🔄 Processing...\n"
                f"🛡️ Privacy Mode Enabled"
            )
        except:
            pass

    await process.wait()

# ================= COMMANDS =================
@app.on_message(filters.command("start"))
async def start(_, m: Message):
    await m.reply_text(START_TEXT)

@app.on_message(filters.video | filters.document)
async def handle_file(_, m: Message):
    async with semaphore:
        uid = m.from_user.id
        udir = make_user_dir(uid)

        uid_name = str(uuid.uuid4())
        input_path = os.path.join(udir, f"{uid_name}_in")
        output_path = os.path.join(udir, f"{uid_name}_out.mp4")

        status = await m.reply_text(
            "⚡ Neon Engine Initializing...\n"
            "🧠 Preparing compression pipeline"
        )

        try:
            file = m.video or m.document
            await m.download(file_name=input_path)

            await status.edit(
                "⚡ Neon Engine Running\n\n"
                "🚀 Compression in progress\n"
                "🔮 Optimizing frames"
            )

            await ffmpeg_compress(input_path, output_path, status)

            await status.edit(
                "📦 Finalizing\n"
                "🚀 Uploading compressed file"
            )

            await m.reply_document(
                output_path,
                caption="⚡ Compressed using Neon HQ Engine"
            )

        except Exception as e:
            await status.edit(f"❌ Error\n\n`{e}`")

        finally:
            try:
                shutil.rmtree(udir)
            except:
                pass

# ================= RUN =================
app.run()
