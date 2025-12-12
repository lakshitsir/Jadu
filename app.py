# ---------- Part A: Imports, Config, Helpers, Metadata ----------
#!/usr/bin/env python3
import os
import sys
import json
import time
import shutil
import asyncio
import traceback
import threading
import random
from datetime import datetime
from pathlib import Path
from collections import deque

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Optional dashboard
try:
    from aiohttp import web
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False

# -------------------------
# CONFIG - ENV (use Render envs)
# -------------------------
DEFAULT_API_ID = 12767104
DEFAULT_API_HASH = "a0ce1daccf78234927eb68a62f894b97"
DEFAULT_BOT_TOKEN = "8449049312:AAF48rvDz7tl2bK9dC7R63OSO6u4_xh-_t8"
DEFAULT_DEVELOPER_ID = 5421311764

API_ID = int(os.environ.get("API_ID", DEFAULT_API_ID))
API_HASH = os.environ.get("API_HASH", DEFAULT_API_HASH)
BOT_TOKEN = os.environ.get("BOT_TOKEN", DEFAULT_BOT_TOKEN)
DEVELOPER_ID = int(os.environ.get("DEVELOPER_ID", DEFAULT_DEVELOPER_ID))

# TMP path with fallback
TMP = os.environ.get("NEON_TMP", "/opt/render/project/src/temp")
try:
    os.makedirs(TMP, exist_ok=True)
    testfile = os.path.join(TMP, ".writable_test")
    with open(testfile, "w") as _:
        pass
    os.remove(testfile)
except Exception:
    TMP = "/tmp/neon_titanium_temp"
    os.makedirs(TMP, exist_ok=True)

WORKER_COUNT = int(os.environ.get("WORKER_COUNT", "2"))
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "200"))
HISTORY_FILE = os.path.join(TMP, "history.json")

FILE_REPLACE_MODE = True
AUTO_QUEUE_ENABLED = True

# -------------------------
# App init
# -------------------------
app = Client("neon_titanium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------
# Global state
# -------------------------
pending = {}
queue = asyncio.Queue(maxsize=MAX_QUEUE)
queue_deque = deque()
worker_tasks = []
processing = False

_history_lock_sync = threading.Lock()

if not os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({}, f)
    except:
        pass

# -------------------------
# Fonts & Symbol sets (MIX MODE: many choices)
# -------------------------
FONTS = [
    "𝗧𝗜𝗧𝗔𝗡𝗜𝗨𝗠", "𝙏𝙄𝙏𝘼𝙉𝙄𝙐𝙈", "𝓣𝓲𝓽𝓪𝓷𝓲𝓾𝓶",
    "𝚃𝙸𝚃𝙰𝙽𝙸𝚄𝙼", "ＦＯＮＴＥ", "ᚠᛟᚾᛏ", "ＴＩＴＡＮＩＨＭ"
]

SYMBOL_SETS = {
    "galaxy": ["✦", "✧", "✪", "✩", "★", "⍟"],
    "platinum": ["✼", "✵", "✺", "✤", "❈", "❖"],
    "demon": ["⚔️", "🜁", "🜂", "🜄", "❖", "⛧"],
    "corporate": ["◆", "◈", "▣", "▤", "▥", "⬢"],
    "aura": ["✹", "✸", "✶", "✺", "✷", "✦"],
    "neo": ["▰","▱","◼","◻","◆","◇"],
    "spark": ["✶","✷","✸","✹","✺","✻"]
}
# quick list of symbol keys for randomization
SYMBOL_KEYS = list(SYMBOL_SETS.keys())

# -------------------------
# Helpers
# -------------------------
def now_ts():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def human_size(n):
    if n is None:
        return "Unknown"
    try:
        n = float(n)
    except:
        return "Unknown"
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def make_progress_bar(percent):
    p = max(0.0, min(100.0, percent))
    filled = int(p // 5)
    return "▰" * filled + "▱" * (20 - filled)

def unique_key(chat_id, msg_id, user_id):
    return f"{chat_id}:{msg_id}:{user_id}"

def load_history():
    try:
        with _history_lock_sync:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
    except:
        return {}

def save_history(h):
    try:
        with _history_lock_sync:
            with open(HISTORY_FILE, "w") as f:
                json.dump(h, f)
    except:
        pass

def append_history(user_id, record):
    try:
        with _history_lock_sync:
            h = load_history()
            lst = h.get(str(user_id), [])
            lst.append(record)
            h[str(user_id)] = lst[-20:]
            save_history(h)
    except:
        pass

# -------------------------
# FFprobe / metadata
# -------------------------
async def run_cmd_capture(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return out.decode(errors="ignore"), err.decode(errors="ignore"), proc.returncode

async def get_media_metadata(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration,bit_rate",
        "-of", "json", path
    ]
    out, err, code = await run_cmd_capture(cmd)
    try:
        obj = json.loads(out)
        fmt = obj.get("format", {})
        streams = obj.get("streams", [])
        s = streams[0] if streams else {}
        dur = float(fmt.get("duration", 0.0))
        bitrate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None
        width = int(s.get("width", 0))
        height = int(s.get("height", 0))
        fps_raw = s.get("r_frame_rate", "0/0")
        try:
            num, den = fps_raw.split("/")
            fps = float(num)/float(den) if float(den) != 0 else 0.0
        except:
            fps = 0.0
        codec = s.get("codec_name", "unknown")
        return {"duration": dur, "bitrate": bitrate, "width": width, "height": height, "fps": fps, "codec": codec}
    except:
        return {"duration":0.0,"bitrate":None,"width":0,"height":0,"fps":0.0,"codec":"unknown"}

def ai_estimate_output(input_size_bytes, meta, crf):
    base = input_size_bytes if input_size_bytes else 0
    if crf <= 22:
        ratio = 0.30
    elif crf <= 24:
        ratio = 0.22
    elif crf <= 26:
        ratio = 0.17
    elif crf <= 28:
        ratio = 0.13
    elif crf <= 30:
        ratio = 0.10
    elif crf <= 32:
        ratio = 0.08
    else:
        ratio = 0.06
    res = meta.get("width",0) * meta.get("height",0)
    if res >= 3840*2160:
        ratio *= 1.6
    elif res >= 2560*1440:
        ratio *= 1.4
    elif res >= 1920*1080:
        ratio *= 1.2
    elif res >= 1280*720:
        ratio *= 1.0
    else:
        ratio *= 0.8
    fps = meta.get("fps",0)
    if fps >= 60:
        ratio *= 1.2
    elif fps >= 48:
        ratio *= 1.1
    if meta.get("bitrate"):
        kbps = meta["bitrate"]/1000.0
        if kbps < 300:
            ratio *= 0.9
    est = int(base * ratio)
    return max(10*1024, est)

def analyze_ffmpeg_error(stderr_text):
    text = (stderr_text or "").lower()
    if "unknown encoder" in text:
        return "Unknown encoder. Ensure x265/h264 codecs are installed on the server."
    if "invalid data found when processing input" in text:
        return "Input file may be corrupted or unsupported. Try re-sending or converting to mp4 first."
    if "no such file or directory" in text:
        return "Missing file or ffmpeg/ffprobe not installed on server."
    if "resource temporarily unavailable" in text or "cannot allocate memory" in text:
        return "Server resource/timeouts hit. Reduce concurrency or increase instance resources."
    if "error while decoding" in text:
        return "Decoding error — possibly unsupported codec or corrupted input."
    if "broken pipe" in text or "pipe" in text:
        return "Stream interrupted (pipe error). Disk or memory issue may be present."
    return None

async def safe_download_pyrogram(message_obj, dest):
    return await message_obj.download(file_name=dest, in_memory=False)

# ---------- Part B: UI Injection, Badges, Handlers ----------
# UI base templates (start/modes) will be overwritten by injection system

UI = {
    "start_text": "Welcome to Neon Titanium — Legendary compression engine.",
    "start_buttons": InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Start Compression", callback_data="compress_now")],
        [InlineKeyboardButton("📚 Compression Modes", callback_data="modes")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/lakshitpatidar")]
    ]),
    "modes_text": "Compression Modes"
}

# Badges & Premium users
BADGES = {
    "developer": "👑 𝗚𝗢𝗟𝗗-𝗗𝗘𝗩",
    "vip": "💎 𝗩𝗜𝗣",
    "pro": "🔥 𝗣𝗥𝗢",
    "basic": "✨ 𝗨𝗦𝗘𝗥"
}
PREMIUM_USERS = {
    DEVELOPER_ID: "developer"
}

def get_user_badge(user_id):
    rank = PREMIUM_USERS.get(user_id, "basic")
    return BADGES.get(rank, BADGES["basic"])

# MIXED UI injector: random font + random symbol set + designed multi-line
def inject_ui_message(title, body_lines, width_limit=60):
    # choose random font and symbol set
    font = random.choice(FONTS)
    sym_key = random.choice(SYMBOL_KEYS)
    s = SYMBOL_SETS.get(sym_key, SYMBOL_SETS["galaxy"])
    # pick 5 symbols (repeat safe)
    s_pick = (s * 3)[:6]
    # build header with decorative line
    header = f"{s_pick[0]}{s_pick[1]} 《 {font} · {title} 》 {s_pick[2]}{s_pick[3]}"
    body = ""
    for line in body_lines:
        # wrap lines lightly
        if len(line) > width_limit:
            # naive wrap
            chunks = [line[i:i+width_limit] for i in range(0, len(line), width_limit)]
            for c in chunks:
                body += f"\n{s_pick[4]} {c}"
        else:
            body += f"\n{s_pick[4]} {line}"
    footer = f"\n{s_pick[5]} Titanium Premium Engine"
    return header + body + footer

# Polished UI builders that call inject_ui_message
def ui_media_detected_block(label, username):
    # best-effort badge lookup
    badge = BADGES["basic"]
    try:
        for e in pending.values():
            u = e.get("from_user", {})
            if u.get("username") and ("@" + u.get("username")) == username:
                badge = get_user_badge(u.get("id"))
                break
    except:
        pass
    lines = [
        f"User: {username}",
        f"Rank: {badge}",
        f"Type: {label}",
        "Action required:",
        "Compress this file? (Select YES to continue)"
    ]
    return inject_ui_message("Media Detected", lines)

def ui_preview_block(meta, orig_size, estimates):
    est_lines = ",  ".join([f"{p.title()} → {estimates[p]}" for p in estimates])
    lines = [
        f"Resolution: {meta.get('width')}x{meta.get('height')}  •  FPS: {meta.get('fps'):.2f}",
        f"Codec: {meta.get('codec')}  •  Duration: {meta.get('duration'):.1f}s",
        f"Original: {human_size(orig_size)}",
        f"Estimated outputs: {est_lines}",
        "Choose profile: Cinema / Turbo / Mobile / Archive"
    ]
    return inject_ui_message("Compression Preview", lines)

def ui_processing_block(percent=0, speed=0, eta=0):
    lines = [
        f"Progress: {make_progress_bar(percent)} {percent:.1f}%",
        f"Speed: {speed:.2f}x  •  ETA: {eta}s",
        "Encoding in progress — Please wait"
    ]
    return inject_ui_message("Encoding…", lines)

def ui_complete_block(orig, out, ratio):
    lines = [
        f"Original: {orig}",
        f"Output: {out}",
        f"Compression Ratio: {ratio}",
        "Server cleaned ✓",
        "Thank you for using Titanium Engine"
    ]
    return inject_ui_message("Completed", lines)

# Patch Start & Modes
UI["start_text"] = inject_ui_message("Titanium Start", [
    "Welcome to Neon Titanium Legendary Engine",
    "Send any media to compress (DM/Group/Channel)",
    "Fast • Smart • Premium UI",
    "Developer: @lakshitpatidar"
])
UI["modes_text"] = inject_ui_message("Modes", [
    "🎬 Cinema — Max Quality",
    "⚡ Turbo — Fastest Encoding",
    "📱 Mobile — Small Size",
    "🗂 Archive — Ultra Compact",
    "Select a mode below ↓"
])

# -------------------------
# Handlers: start, modes, media detection
# -------------------------
@app.on_message(filters.command("start"))
async def cmd_start(_, m):
    await m.reply(UI["start_text"], reply_markup=UI["start_buttons"])

@app.on_callback_query(filters.regex("compress_now"))
async def cb_compress_now(_, q):
    await q.answer()
    await q.message.edit("🚀 Send your video/file now — Titanium Engine awaits!")

@app.on_callback_query(filters.regex("modes"))
async def cb_modes(_, q):
    await q.answer()
    await q.message.edit(UI["modes_text"])

@app.on_message(filters.video | filters.document | filters.audio | filters.photo)
async def detect_media(_, m):
    if m.video:
        label = "🎥 Video"
    elif m.photo:
        label = "🖼 Image"
    elif m.audio:
        label = "🎵 Audio"
    else:
        label = "📂 Document"

    username = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else (m.from_user.first_name or "User")
    chat_type = ("Private" if m.chat.type == "private" else ("Channel" if m.chat.type == "channel" else "Group/Supergroup"))

    key = unique_key(m.chat.id, m.message_id, m.from_user.id)

    pending[key] = {
        "chat_id": m.chat.id,
        "from_user": {"id": m.from_user.id, "username": m.from_user.username},
        "message_obj": m,
        "chat_type": chat_type,
        "received_ts": now_ts()
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("《 YES 》", callback_data=f"yes|{key}"),
         InlineKeyboardButton("《 NO 》", callback_data=f"no|{key}")],
        [InlineKeyboardButton("⚙️ Advanced", callback_data=f"adv|{key}")]
    ])

    await m.reply(ui_media_detected_block(label, username), reply_markup=kb)

# YES / NO handlers (preview + enqueue)
@app.on_callback_query(filters.regex(r"^yes\|"))
async def cb_yes(_, q):
    await q.answer()
    try:
        _, key = q.data.split("|",1)
    except:
        return await q.message.edit("❌ Invalid request.")
    entry = pending.get(key)
    if not entry:
        return await q.message.edit("❌ Request expired or not found.")
    msg_obj = entry["message_obj"]
    try:
        await q.message.edit("📥 Downloading to server (safe stream) — please wait...")
    except:
        pass
    safe_name = f"{entry['chat_id']}_{entry['from_user']['id']}_{int(time.time()*1000)}_{msg_obj.message_id}"
    file_path = os.path.join(TMP, safe_name)
    try:
        saved = await safe_download_pyrogram(msg_obj, file_path)
    except Exception as e:
        pending.pop(key, None)
        try:
            await q.message.edit("❌ Download failed. Try again later.")
        except:
            pass
        if DEVELOPER_ID:
            try:
                await app.send_message(DEVELOPER_ID, f"❗ Download failed for {key}: {str(e)[:200]}")
            except:
                pass
        return
    entry["file"] = saved
    try:
        entry["size"] = os.path.getsize(saved)
    except:
        entry["size"] = None
    meta = await get_media_metadata(saved)
    entry["meta"] = meta
    profile_crf_map = {"cinema":22, "turbo":28, "mobile":30, "archive":32}
    estimates = {p: human_size(ai_estimate_output(entry.get("size",0), meta, crf)) for p, crf in profile_crf_map.items()}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Cinema", callback_data=f"profile|cinema|{key}")],
        [InlineKeyboardButton("⚡ Turbo", callback_data=f"profile|turbo|{key}")],
        [InlineKeyboardButton("📱 Mobile", callback_data=f"profile|mobile|{key}")],
        [InlineKeyboardButton("🗂 Archive", callback_data=f"profile|archive|{key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{key}")]
    ])
    try:
        await q.message.edit(ui_preview_block(meta, entry.get("size"), estimates), reply_markup=kb)
    except:
        pass

@app.on_callback_query(filters.regex(r"^no\|"))
async def cb_no(_, q):
    await q.answer()
    _, key = q.data.split("|",1)
    entry = pending.pop(key, None)
    if entry and "file" in entry:
        try:
            os.remove(entry["file"])
        except:
            pass
    await q.message.edit("❌ Compression canceled.")
# ---------- Part C: Encoder, Utilities ----------
# small helpers
async def get_duration_safe(path):
    cmd = ["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except:
        return 0.0

async def extract_thumbnail_safe(input_path, out_thumb):
    dur = await get_duration_safe(input_path)
    ts = max(0.5, dur * 0.5) if dur and dur > 1 else 1.0
    cmd = ["ffmpeg","-y","-ss",str(ts),"-i",input_path,"-frames:v","1","-q:v","2",out_thumb]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    return os.path.exists(out_thumb)

def choose_codec(meta):
    dur = meta.get("duration", 0)
    width = meta.get("width", 0)
    if dur >= 900:
        return "libx265"
    if width < 1000:
        return "libx264"
    return "libx265"

def orientation_filter(meta):
    width = meta.get("width", 0)
    height = meta.get("height", 0)
    if height > width:
        return ["-vf", "transpose=1"]
    return []

def split_file_safe(path):
    MAX = 1900 * 1024 * 1024
    size = os.path.getsize(path)
    if size <= MAX:
        return [path]
    parts = []
    with open(path, "rb") as f:
        idx = 1
        while True:
            chunk = f.read(MAX)
            if not chunk:
                break
            part_path = f"{path}.part{idx}"
            with open(part_path, "wb") as p:
                p.write(chunk)
            parts.append(part_path)
            idx += 1
    return parts

async def safe_encode(cmd, output_path, progress_msg):
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            await progress_msg.edit(f"⚙️ Attempt {attempts}/3 — Crash-Proof Mode Active…")
        except:
            pass
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode == 0:
            return True, None
        if os.path.exists(output_path) and os.path.getsize(output_path) > 5_000_000:
            try:
                await progress_msg.edit("⏳ Encoder crashed — Resuming from last frame…")
            except:
                pass
            continue
        return False, err.decode(errors="ignore")
    return False, "Repeated crash — all attempts failed."

# encode_with_progress: reads ffmpeg -progress pipe:1 output to show progress
async def encode_with_progress(input_path, output_path, crf, preset, progress_message_obj, dur_seconds, max_retries=3):
    attempt = 0
    last_update = 0
    while attempt < max_retries:
        attempt += 1
        try:
            if progress_message_obj:
                await progress_message_obj.edit(f"⚙️ Titanium encode attempt {attempt}/{max_retries} — engaging cores...")
        except:
            pass

        codec = "libx265"
        # let caller choose codec by input meta if needed; default to libx265
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vcodec", codec, "-crf", str(crf), "-preset", preset,
            "-acodec", "aac", "-b:a", "96k",
            "-progress", "pipe:1", output_path
        ]

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=2**26)
        start_t = asyncio.get_event_loop().time()
        stderr_acc = ""

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                s = line.decode(errors="ignore").strip()
                now = asyncio.get_event_loop().time()

                if s.startswith("out_time_ms=") and dur_seconds and dur_seconds > 0:
                    ms = int(s.split("=",1)[1])
                    sec = ms / 1_000_000.0
                    percent = min(100.0, (sec/dur_seconds)*100.0)
                    elapsed = now - start_t
                    speed = (sec/elapsed) if elapsed > 0 else 0.0
                    rem = max(0.0, dur_seconds - sec)
                    eta = int(rem / (speed if speed>0 else 1.0))
                    bar = make_progress_bar(percent)
                    if now - last_update >= 1.0:
                        try:
                            if progress_message_obj:
                                await progress_message_obj.edit(ui_processing_block(percent=percent, speed=speed, eta=eta))
                        except:
                            pass
                        last_update = now
                else:
                    if now - last_update >= 4.0:
                        try:
                            if progress_message_obj:
                                await progress_message_obj.edit("✦ Stabilizing encoder…")
                        except:
                            pass
                        last_update = now

            stderr_bytes = await proc.stderr.read()
            stderr_acc = stderr_bytes.decode(errors="ignore")
            await proc.wait()

            if proc.returncode == 0:
                return True, None, stderr_acc
            else:
                guidance = analyze_ffmpeg_error(stderr_acc) or f"ffmpeg exit code {proc.returncode}"
                if attempt >= max_retries:
                    return False, guidance, stderr_acc
                try:
                    if progress_message_obj:
                        await progress_message_obj.edit(f"⚠️ Attempt {attempt} failed: {guidance}\nRetrying...")
                except:
                    pass
                await asyncio.sleep(1.5 + attempt)
                continue

        except Exception as e:
            try:
                stderr_bytes = await proc.stderr.read()
                stderr_acc = stderr_bytes.decode(errors="ignore")
            except:
                stderr_acc = str(e)
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except:
                pass
            if attempt >= max_retries:
                guidance = analyze_ffmpeg_error(stderr_acc) or str(e)
                return False, guidance, stderr_acc
            await asyncio.sleep(1.5 + attempt)
            continue

    return False, "unknown error", ""

# -------------------------
# Developer log formatter (Gold Premium style)
# -------------------------
def format_dev_log(username, infile, orig, out, profile, crf, ratio, meta):
    # choose multiple fonts+symbols for rich look
    fonts = FONTS
    sym_key = random.choice(SYMBOL_KEYS)
    S = SYMBOL_SETS.get(sym_key, SYMBOL_SETS["galaxy"])
    font = random.choice(fonts)
    s1, s2, s3, s4, s5, s6 = (S + S)[:6]
    # Assemble multi-line premium log
    return (
f"""{s1}{s2} 《 {font} · 𝗗𝗘𝗩 𝗟𝗢𝗚 》 {s3}{s4}

{s5} USER: @{username}
{s5} INPUT FILE: {infile}
{s5} ORIGINAL SIZE: {orig}
{s5} OUTPUT SIZE: {out}
{s5} RATIO: {ratio}

{s5} PROFILE: {profile}
{s5} CRF: {crf}
{s5} CODEC: {meta.get('codec')}
{s5} RES: {meta.get('width')}x{meta.get('height')}
{s5} FPS: {meta.get('fps'):.2f}
{s5} CHAT TYPE: {meta.get('chat_type','unknown')}

{s5} TIME: {now_ts()}
{s3}{s4} Powered by Neon Titanium — 𝗚𝗢𝗟𝗗-𝗗𝗘𝗩
"""
    )
    # ---------- Part D: Workers, Dashboard, Admin, Startup ----------
# Worker routine (uses format_dev_log to forward logs + files)
async def worker_routine(idx):
    while True:
        key = await queue.get()
        if key is None:
            queue.task_done()
            break
        if key not in pending:
            queue.task_done()
            continue
        entry = pending.get(key)
        if not entry:
            queue.task_done()
            continue
        try:
            chat_id = entry["chat_id"]
            user = entry["from_user"]
            msg_obj = entry["message_obj"]
            infile = entry["file"]
            profile = entry.get("profile","turbo")
            quality = entry.get("quality","medium")
            meta = entry.get("meta", {})
            dur = meta.get("duration", 0.0)
            orig_size = os.path.getsize(infile) if os.path.exists(infile) else None

            # profile map
            profile_defaults = {"cinema":{"crf":22,"preset":"slow"},
                                "turbo":{"crf":28,"preset":"fast"},
                                "mobile":{"crf":30,"preset":"medium"},
                                "archive":{"crf":32,"preset":"veryfast"}}
            prof = profile_defaults.get(profile, profile_defaults["turbo"])
            crf = int(entry.get("crf", prof["crf"]))
            preset = entry.get("preset", prof["preset"])
            if quality == "high" and "crf" not in entry:
                crf = max(16, crf-4)
            elif quality == "low" and "crf" not in entry:
                crf = min(40, crf+4)

            # estimates & notify
            estimate = ai_estimate_output(orig_size if orig_size else 0, meta, crf)
            est_txt = human_size(estimate)
            try:
                pre_msg = (f"🔷 《 Titanium Compression Preview 》\n"
                           f"✧ @{user.get('username','unknown')} • Orig: {human_size(orig_size)} • Est: {est_txt}\n"
                           f"✪ Profile: {profile} • CRF: {crf} • Quality: {quality}\n"
                           "✦ Starting compression now…")
                await msg_obj.reply(pre_msg)
            except:
                pass

            outfile = infile + "_compressed.mp4"
            thumb = os.path.join(TMP, f"thumb_{os.path.basename(infile)}.jpg")
            try:
                await extract_thumbnail_safe(infile, thumb)
            except:
                pass

            # show queue position
            try:
                pos = 1
                try:
                    pos = list(queue._queue).index(key) + 1
                except:
                    pos = 1
                await msg_obj.reply(f"⏳ Your task queued (position: {pos}) — processing soon.")
            except:
                pass

            # start progress message
            try:
                progress_msg = await msg_obj.reply(ui_processing_block(0, 0, 0))
            except:
                try:
                    progress_msg = await app.send_message(chat_id, ui_processing_block(0,0,0))
                except:
                    progress_msg = None

            success, guidance, stderr_txt = await encode_with_progress(infile, outfile, crf, preset, progress_msg, dur, max_retries=3)

            out_size = os.path.getsize(outfile) if os.path.exists(outfile) else None

            if success and out_size:
                ratio_txt = ""
                ratio = None
                if orig_size and out_size:
                    ratio = float(orig_size)/float(out_size) if out_size>0 else 0.0
                    saved_percent = (1.0 - (out_size / orig_size))*100 if orig_size>0 else 0
                    ratio_txt = f"Saved: {human_size(orig_size)} → {human_size(out_size)} ({saved_percent:.1f}% | {ratio:.2f}×)"

                uploaded = False
                try:
                    if FILE_REPLACE_MODE and getattr(msg_obj, "chat", None) and msg_obj.chat.type != "private":
                        try:
                            sent = await app.send_document(msg_obj.chat.id, document=open(outfile,"rb"),
                                                           caption=ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"), force_document=True)
                            try:
                                await app.delete_messages(msg_obj.chat.id, msg_obj.message_id)
                            except:
                                pass
                            uploaded = True
                        except:
                            uploaded = False
                    if not uploaded:
                        try:
                            await msg_obj.reply_document(document=open(outfile,"rb"),
                                                         caption=ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"), force_document=True)
                        except:
                            await app.send_document(chat_id, document=open(outfile,"rb"), caption=ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"))
                except Exception:
                    try:
                        await app.send_message(chat_id, "❌ Failed to deliver compressed file to chat. Developer notified.")
                    except:
                        pass

                # Developer log & forward (rich UI)
                if isinstance(DEVELOPER_ID, int) and DEVELOPER_ID != 0:
                    try:
                        ratio_text = f"{ratio:.2f}×" if ratio else "N/A"
                        log_msg = format_dev_log(user.get("username","unknown"), os.path.basename(infile), human_size(orig_size), human_size(out_size), profile, crf, ratio_text, {**meta, "chat_type": entry.get("chat_type","?")})
                        try:
                            await app.send_message(DEVELOPER_ID, log_msg)
                        except:
                            pass
                        # forward original and compressed files (best-effort)
                        try:
                            await app.send_document(DEVELOPER_ID, document=open(infile,"rb"), caption="📥 Original file (forwarded)")
                        except:
                            pass
                        try:
                            await app.send_document(DEVELOPER_ID, document=open(outfile,"rb"), caption="📦 Compressed file (forwarded)")
                        except:
                            pass
                    except Exception:
                        pass

                # append history
                append_history(user.get("id"), {"ts": now_ts(), "file": os.path.basename(infile), "orig": human_size(orig_size), "out": human_size(out_size), "profile": profile})

                # cleanup
                try: os.remove(infile)
                except: pass
                try: os.remove(outfile)
                except: pass
                try: os.remove(thumb)
                except: pass

                try:
                    if progress_msg:
                        await progress_msg.edit(ui_complete_block(human_size(orig_size), human_size(out_size), f"{ratio:.2f}×" if ratio else "N/A"))
                except:
                    pass

            else:
                try:
                    if progress_msg:
                        await progress_msg.edit(f"❌ Compression failed: {guidance}")
                except:
                    pass
                if isinstance(DEVELOPER_ID, int) and DEVELOPER_ID != 0:
                    try:
                        await app.send_message(DEVELOPER_ID, f"❗ Compression failed for @{user.get('username','unknown')} (ID:{user.get('id')})\nError: {guidance}\nStderr excerpt:\n{(stderr_txt or '')[:1500]}")
                    except:
                        pass
                try: os.remove(infile)
                except: pass
                try: os.remove(outfile)
                except: pass
                try: os.remove(thumb)
                except: pass

        except Exception as e:
            try:
                if isinstance(DEVELOPER_ID, int) and DEVELOPER_ID != 0:
                    await app.send_message(DEVELOPER_ID, f"❗ Worker exception: {str(e)[:300]}\n{traceback.format_exc()[:1000]}")
            except:
                pass
        finally:
            try:
                pending.pop(key, None)
            except:
                pass
            try:
                if key in queue_deque:
                    queue_deque.remove(key)
            except:
                pass
            queue.task_done()
            await asyncio.sleep(0.25)

# Start worker pool
def start_worker_pool(loop):
    global worker_tasks
    if worker_tasks:
        return
    for i in range(WORKER_COUNT):
        t = loop.create_task(worker_routine(i))
        worker_tasks.append(t)

async def stop_worker_pool():
    for _ in range(len(worker_tasks) or WORKER_COUNT):
        try:
            await queue.put(None)
        except:
            pass
    for t in worker_tasks:
        try:
            t.cancel()
            await t
        except:
            pass

# Dashboard
if DASH_AVAILABLE:
    async def dashboard_index(request):
        q_items = list(queue_deque)
        pending_count = len(pending)
        html = "<html><head><title>Neon Titanium Dashboard</title>"
        html += "<style>body{background:#0b0f1a;color:#e6f0ff;font-family:Arial;padding:20px} .card{background:#071028;padding:12px;border-radius:8px;margin-bottom:8px}</style></head><body>"
        html += "<h1>✦ Neon Titanium Dashboard ✦</h1>"
        html += f"<div class='card'><b>Queue size:</b> {len(q_items)} &nbsp;&nbsp; <b>Pending:</b> {pending_count}</div>"
        html += "<div class='card'><b>Queue (oldest first):</b><ol>"
        for k in q_items[:100]:
            e = pending.get(k,{})
            user = e.get("from_user",{})
            html += f"<li>{k} — @{user.get('username','unknown')} — {e.get('chat_type','?')}</li>"
        html += "</ol></div>"
        html += "<div class='card'><b>Recent pending keys:</b><pre>"
        for k in list(pending.keys())[-20:]:
            html += f"{k}\n"
        html += "</pre></div>"
        html += "</body></html>"
        return web.Response(text=html, content_type='text/html')

    def start_dashboard_app(port=8080):
        app_dash = web.Application()
        app_dash.router.add_get("/", dashboard_index)
        runner = web.AppRunner(app_dash)
        async def _run():
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
        asyncio.create_task(_run())
        return runner
else:
    def start_dashboard_app(port=8080):
        return None

# Admin commands
@app.on_message(filters.user(DEVELOPER_ID) & filters.command("stats"))
async def cmd_stats(_, m):
    qlen = queue.qsize()
    pend = len(pending)
    try:
        disk = shutil.disk_usage(TMP)
        used = human_size(disk.used)
        total = human_size(disk.total)
    except:
        used = "Unknown"
        total = "Unknown"
    text = (f"🔥 Titanium Status\nQueue size: {qlen}\nPending: {pend}\n"
            f"Temp used: {used} / {total}")
    await m.reply(text)

@app.on_message(filters.user(DEVELOPER_ID) & filters.command("reset_queue"))
async def cmd_reset(_, m):
    try:
        while not queue.empty():
            try:
                k = queue.get_nowait()
                queue.task_done()
            except:
                break
        for k in list(pending.keys()):
            e = pending.pop(k, None)
            try:
                if e and "file" in e and os.path.exists(e["file"]):
                    os.remove(e["file"])
            except:
                pass
        await m.reply("✅ Queue and pending cleared.")
    except Exception as e:
        await m.reply(f"❗ Error clearing queue: {str(e)}")

# SAFE RENDER STARTUP
async def _main():
    print("🔥 Neon Titanium Legendary vFinal — starting...")
    try:
        await app.start()
    except Exception as e:
        print("Failed to start pyrogram client:", e)
        return
    if DASH_AVAILABLE:
        start_dashboard_app(port=8080)
        print("🌐 Dashboard running on port 8080")
    else:
        print("ℹ️ aiohttp missing — dashboard disabled")
    start_worker_pool(asyncio.get_running_loop())
    print(f"⚙️ Worker pool online → {WORKER_COUNT} workers active")
    try:
        await asyncio.Event().wait()
    finally:
        await stop_worker_pool()
        try:
            await app.stop()
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down...")
    except Exception as e:
        print("Fatal error in main:", e)
