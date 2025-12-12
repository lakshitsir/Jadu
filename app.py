import os
import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

# ------------------------
# MANUAL CONFIG
# ------------------------
API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"

# Compression settings
MAX_CONCURRENT_JOBS = 1
FFMPEG_PRESET = "veryfast"
CRF = "28"

# Temp folder
TMP_DIR = Path("neon_tmp").resolve()
TMP_DIR.mkdir(exist_ok=True)

# IMPORTANT FIX → rename client variable
bot = Client(
    "neon_fixed_compressor",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Job control
job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
job_meta: Dict[str, dict] = {}
running_jobs: Dict[str, asyncio.Task] = {}

START_TEXT = "🔥 Neon HQ Compressor Online\nSend any video!"

PROMPT_KBD = InlineKeyboardMarkup([
    [InlineKeyboardButton("YES", callback_data="comp_yes")],
    [InlineKeyboardButton("NO", callback_data="comp_no")]
])


# ------------------------
# Helper functions
# ------------------------

def human(x):
    return x / (1024 * 1024)


def ffmpeg_compress(i, o):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", i,
        "-vcodec", "libx265",
        "-crf", CRF,
        "-preset", FFMPEG_PRESET,
        "-acodec", "aac",
        "-b:a", "96k",
        o
    ])


async def download_with_progress(client, msg, dest, edit_msg):
    last = 0

    def cb(cur, tot):
        nonlocal last
        now = asyncio.get_event_loop().time()
        if now - last >= 1:
            last = now
            percent = cur / tot * 100
            asyncio.create_task(
                edit_msg.edit(f"⬇️ Downloading {percent:.1f}%\n{human(cur):.2f}/{human(tot):.2f} MB")
            )

    await client.download_media(msg, file_name=str(dest), progress=cb)
    return dest


async def upload_with_progress(client, chat_id, path, caption, edit_msg):
    total = path.stat().st_size
    last = 0

    async def cb(cur, tot):
        nonlocal last
        now = asyncio.get_event_loop().time()
        if now - last >= 1:
            last = now
            percent = cur / tot * 100
            await edit_msg.edit(
                f"⬆️ Uploading {percent:.1f}%\n{human(cur):.2f}/{human(tot):.2f} MB"
            )

    await client.send_document(chat_id, document=str(path), caption=caption, progress=cb)


# ------------------------
# Processing worker
# ------------------------

async def process_job(client, jid):
    meta = job_meta[jid]

    chat_id = meta["chat_id"]
    name = meta["name"]
    msg_obj = meta["msg_obj"]

    async with job_semaphore:
        status = await client.send_message(chat_id, f"🎛 Starting: {name}")

        try:
            temp_in = TMP_DIR / f"{jid}_in"
            temp_out = TMP_DIR / f"{jid}_out.mp4"

            downloaded = await download_with_progress(client, msg_obj, temp_in, status)
            orig = downloaded.stat().st_size

            await status.edit("⚙️ Compressing…")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, ffmpeg_compress, str(downloaded), str(temp_out))

            new = temp_out.stat().st_size

            caption = f"🎥 Compressed: {name}\nSaved: {100 - (new/orig*100):.1f}%"
            await upload_with_progress(client, chat_id, temp_out, caption, status)

            await status.edit(
                f"✅ Done!\nOriginal: {human(orig):.2f} MB\nNew: {human(new):.2f} MB"
            )

        except Exception as e:
            await status.edit(f"❌ Error: {e}")

        finally:
            try:
                if temp_in.exists(): temp_in.unlink()
                if temp_out.exists(): temp_out.unlink()
            except:
                pass

            job_meta.pop(jid, None)
            running_jobs.pop(jid, None)


# ------------------------
# Handlers
# ------------------------

@bot.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(START_TEXT)


@bot.on_message(filters.private & (filters.video | filters.document))
async def media_detect(_, m):

    name = (
        m.document.file_name if m.document else
        m.video.file_name
    )

    size = (
        m.document.file_size if m.document else
        m.video.file_size
    )

    prompt = await m.reply(
        f"📁 {name}\nSize: {human(size):.2f} MB\n\nCompress?",
        reply_markup=PROMPT_KBD
    )

    job_meta[f"prompt_{prompt.id}"] = {
        "chat_id": m.chat.id,
        "name": name,
        "msg_obj": m
    }


@bot.on_callback_query(filters.regex("comp_(yes|no)"))
async def cb_handler(client, cq):
    msg = cq.message
    key = f"prompt_{msg.id}"

    if key not in job_meta:
        await msg.edit("⚠️ Expired.")
        return

    meta = job_meta[key]

    if cq.data == "comp_no":
        await msg.edit("❌ Skipped.")
        job_meta.pop(key, None)
        return

    await msg.edit("⏳ Queued…")

    jid = str(uuid.uuid4())[:8]
    job_meta[jid] = meta
    job_meta.pop(key, None)

    task = asyncio.create_task(process_job(client, jid))
    running_jobs[jid] = task

    await cq.answer("Queued ✔")


# ------------------------
# Run bot
# ------------------------

if __name__ == "__main__":
    print("🔥 Compressor Bot Running…")
    bot.run()
