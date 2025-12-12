#!/usr/bin/env python3
# Neon Compressor Bot — Ultra Aesthetic + AI Output Prediction Edition
# Clean Edition: No Owner Logs

import os
import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Dict

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery


# ------------------------------------
# CONFIG
# ------------------------------------
API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"

CRF = 28                 # ~90% HQ Quality
FFMPEG_PRESET = "faster" # Fast compression
MAX_CONCURRENT_JOBS = 2

TMP_DIR = Path("neon_tmp")
TMP_DIR.mkdir(exist_ok=True)

app = Client(
    "neon_ultra_ai_compressor",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
job_meta: Dict[str, dict] = {}
running_jobs: Dict[str, asyncio.Task] = {}


# ------------------------------------
# UI HELPERS
# ------------------------------------

def human_mb(n: int):
    return n / (1024 * 1024)

def bar(percent):
    filled = int(percent / 100 * 18)
    empty = 18 - filled
    return "▰" * filled + "▱" * empty

async def update_ui(pm, phase, current, total, user):
    percent = (current / total * 100) if total else 0
    ui = (
        f"✨ <b>{phase}</b> — {percent:.1f}%\n"
        f"<code>{bar(percent)}</code>\n"
        f"{human_mb(current):.2f} MB / {human_mb(total):.2f} MB\n"
        f"👤 {user}"
    )

    now = asyncio.get_event_loop().time()
    if not hasattr(update_ui, "t"):
        update_ui.t = 0

    if now - update_ui.t < 0.8:
        return

    update_ui.t = now

    try:
        await pm.edit(ui)
    except:
        pass


# ------------------------------------
# AI OUTPUT SIZE PREDICTION
# ------------------------------------

def ai_predict_size(input_bytes: int):
    """
    Predict compressed size using HEVC expected compression ratio.
    """
    # 65% reduction approx (safe middle value)
    predicted = input_bytes * 0.35
    return predicted


# ------------------------------------
# FFMPEG COMPRESSOR
# ------------------------------------

def ffmpeg_compress(src, out):
    cmd = [
        "ffmpeg","-y",
        "-i",src,
        "-vcodec","libx265",
        "-crf",str(CRF),
        "-preset",FFMPEG_PRESET,
        "-acodec","aac",
        "-b:a","96k",
        out
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------
# DOWNLOAD / UPLOAD
# ------------------------------------

async def download(client, msg, dest, pm, user):
    async def cb(cur, total):
        await update_ui(pm, "Downloading", cur, total, user)
    return Path(await client.download_media(msg, file_name=str(dest), progress=cb))


async def upload(client, chat, file, caption, pm, user):
    async def cb(cur, total):
        await update_ui(pm, "Uploading", cur, total, user)
    await client.send_document(chat, str(file), caption=caption, progress=cb)


# ------------------------------------
# PROCESS JOB
# ------------------------------------

async def process_job(client: Client, job_id: str):

    meta = job_meta[job_id]
    chat = meta["chat"]
    user = meta["user"]
    filename = meta["filename"]

    pm = await client.send_message(chat, f"🔧 <b>Preparing…</b>\n👤 {user}")

    async with job_semaphore:

        tmp_in = TMP_DIR / f"{job_id}_in"
        tmp_out = TMP_DIR / f"{job_id}.mp4"

        try:
            # DOWNLOAD
            f = await download(client, meta["msg"], tmp_in, pm, user)
            orig = f.stat().st_size

            # COMPRESS
            await pm.edit("⚙️ <b>Compressing…</b>")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, ffmpeg_compress, str(f), str(tmp_out))

            # UPLOAD
            new = tmp_out.stat().st_size
            saved = 100 - (new / orig * 100)

            caption = (
                f"🎥 <b>{filename}</b>\n"
                f"Saved: {saved:.1f}%\n"
                f"👤 {user}"
            )

            await upload(client, chat, tmp_out, caption, pm, user)

            await pm.edit(
                f"✅ <b>Done!</b>\n"
                f"Original: {human_mb(orig):.2f} MB\n"
                f"Compressed: {human_mb(new):.2f} MB\n"
                f"Saved: {saved:.1f}%"
            )

        finally:
            for p in [tmp_in, tmp_out]:
                try: p.unlink()
                except: pass

            job_meta.pop(job_id, None)
            running_jobs.pop(job_id, None)


# ------------------------------------
# MEDIA DETECTION + CONFIRMATION (WITH AI PREDICTION)
# ------------------------------------

kbd = InlineKeyboardMarkup([
    [InlineKeyboardButton("✔ Yes — Compress", callback_data="yes")],
    [InlineKeyboardButton("✖ No — Cancel", callback_data="no")]
])

@app.on_message((filters.video | filters.document | filters.audio | filters.photo))
async def detect(client: Client, msg: Message):

    if not msg.from_user:
        return

    user = f"@{msg.from_user.username}" if msg.from_user.username else f"user_{msg.from_user.id}"

    filename = (
        msg.document.file_name if msg.document else
        msg.video.file_name if msg.video else
        msg.audio.file_name if msg.audio else
        "photo.jpg"
    )

    size = (
        msg.document.file_size if msg.document else
        msg.video.file_size if msg.video else
        msg.audio.file_size if msg.audio else
        0
    )

    predicted = ai_predict_size(size)

    prompt = (
        f"🎬 <b>Media Detected</b>\n\n"
        f"📄 <b>{filename}</b>\n"
        f"📦 {human_mb(size):.2f} MB\n\n"
        f"🤖 <b>AI Estimate</b>:\n"
        f"📉 Expected Output: ~{human_mb(predicted):.2f} MB\n\n"
        f"👤 {user}\n\n"
        f"<b>Compress this file?</b>"
    )

    sent = await msg.reply(prompt, reply_markup=kbd)

    job_meta[f"p{sent.message_id}"] = {
        "msg": msg,
        "chat": msg.chat.id,
        "filename": filename,
        "user": user
    }


# ------------------------------------
# CALLBACK HANDLER
# ------------------------------------

@app.on_callback_query(filters.regex("yes|no"))
async def callback(client: Client, q: CallbackQuery):

    key = f"p{q.message.message_id}"

    if key not in job_meta:
        await q.message.edit("⚠️ Expired.")
        return

    if q.data == "no":
        await q.message.edit("❌ Cancelled.")
        job_meta.pop(key, None)
        return

    # YES
    meta = job_meta.pop(key)
    job_id = uuid.uuid4().hex[:8]
    job_meta[job_id] = meta

    running_jobs[job_id] = asyncio.create_task(process_job(client, job_id))

    await q.message.edit("✨ Queued!")


# ------------------------------------
# RUN BOT
# ------------------------------------
if __name__ == "__main__":
    print("🔥 Neon AI Compressor Started (Ultra Aesthetic Edition)")
    app.run()
