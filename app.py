import os
import asyncio
import subprocess
from collections import deque
from pyrogram import Client, filters

# ================= CONFIG =================
API_ID = 12767104
API_HASH = "a0ce1daccf78234927eb68a62f894b97"
BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"

DEV_TAG = "@lakshitpatidar"

WORKDIR = "work"
os.makedirs(WORKDIR, exist_ok=True)

app = Client(
    "neo_compress_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================= UI =================
def ui(status, user):
    return (
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎬 NEO VIDEO COMPRESSOR\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"Request by {user}\n\n"
        f"{status}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"Dev - {DEV_TAG}"
    )

# ================= SAFE EDIT =================
LAST_EDIT = {}
async def safe_edit(msg, text):
    now = asyncio.get_event_loop().time()
    mid = msg.id
    if mid in LAST_EDIT and now - LAST_EDIT[mid] < 1.2:
        await asyncio.sleep(1.2)
    try:
        await msg.edit(text)
        LAST_EDIT[mid] = asyncio.get_event_loop().time()
    except:
        pass

# ================= AUTO QUALITY =================
def auto_params(size_mb: float):
    if size_mb > 2000:
        return 33, "1200k"
    elif size_mb >= 1500:
        return 32, "1400k"
    elif size_mb >= 500:
        return 30, "1800k"
    elif size_mb >= 200:
        return 28, "2200k"
    else:
        return 26, "2500k"

# ================= QUEUE =================
QUEUE = deque()
PROCESSING = False

# ================= START =================
@app.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        "🎬 Neo Video Compressor\n\n"
        "Send video → auto compress\n"
        "Smart quality selection\n\n"
        f"Dev - {DEV_TAG}"
    )

# ================= VIDEO =================
@app.on_message(filters.video)
async def video_in(_, m):
    global PROCESSING

    user = f"@{m.from_user.username}" if m.from_user and m.from_user.username else "User"
    status = await m.reply(ui("Added to queue…", user))

    inp = f"{WORKDIR}/{m.id}.mp4"
    await m.download(file_name=inp)

    size_mb = m.video.file_size / (1024 * 1024)
    crf, maxrate = auto_params(size_mb)

    QUEUE.append({
        "chat": m.chat.id,
        "msg": status,
        "inp": inp,
        "user": user,
        "crf": crf,
        "maxrate": maxrate
    })

    if not PROCESSING:
        PROCESSING = True
        asyncio.create_task(process_queue())

# ================= PROCESS =================
async def process_queue():
    global PROCESSING

    while QUEUE:
        job = QUEUE.popleft()

        msg = job["msg"]
        inp = job["inp"]
        out = inp.replace(".mp4", "_out.mp4")

        await safe_edit(msg, ui("Compressing… Please wait", job["user"]))

        cmd = [
            "ffmpeg", "-y",
            "-i", inp,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(job["crf"]),
            "-maxrate", job["maxrate"],
            "-bufsize", "2M",
            "-c:a", "copy",
            "-threads", "0",
            "-movflags", "+faststart",
            out
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        await app.send_video(
            chat_id=job["chat"],
            video=out,
            caption=f"Compression completed.\n\nDev - {DEV_TAG}"
        )

        os.remove(inp)
        os.remove(out)

        await safe_edit(msg, ui("Done", job["user"]))

    PROCESSING = False

# ================= RUN =================
app.run()
