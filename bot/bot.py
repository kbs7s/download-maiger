"""Download maniger - Telegram bot.

Send it a link (YouTube, Pinterest, Instagram, TikTok, Facebook, X, direct files...)
and it sends the video, the sound (MP3) or the photos back in the chat.

Runs on a server (Oracle Cloud free VM) next to a local Telegram Bot API server,
which lets the bot send files up to 2 GB instead of 50 MB.

Settings come from environment variables (see .env.example).
"""

import asyncio
import logging
import os
import re
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# ------------------------------------------------------------------ settings

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_BASE = os.environ.get("API_BASE", "").rstrip("/")          # e.g. http://telegram-bot-api:8081
LOCAL_MODE = bool(API_BASE)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
WORK_DIR = DATA_DIR / "work"
DB_PATH = DATA_DIR / "bot.db"
COOKIES_FILE = os.environ.get("COOKIES_FILE", "")
MAX_BYTES = (2000 if LOCAL_MODE else 50) * 1024 * 1024
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "3"))
ADMIN_IDS = {int(x) for x in re.findall(r"\d+", os.environ.get("ADMIN_IDS", ""))}
OPEN_TO_ALL = os.environ.get("OPEN_TO_ALL", "") == "1"

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

# ------------------------------------------------------------------ texts (Iraqi Arabic)

TXT = {
    "welcome": "هلا {name} 👋\nدزلي رابط من يوتيوب، بنترست، إنستغرام، تيك توك، فيسبوك، X أو أي رابط ملف، وأرجعلك الفيديو أو الصوت أو الصور هنا.\n\n/history سجل تنزيلاتك\nرقمك: <code>{uid}</code>",
    "not_allowed": "هذا البوت للعائلة فقط 🙏\nدز هذا الرقم لكرار حتى يضيفك:\n<code>{uid}</code>",
    "choose": "شنو تريد من هذا الرابط؟",
    "video": "🎬 فيديو", "audio": "🎵 صوت MP3", "photos": "🖼 صور / ملف",
    "working": "⏳ جاري التنزيل…", "progress": "⏳ جاري التنزيل… {pct}\n{done} من {total}",
    "uploading": "📤 جاري الإرسال…",
    "failed": "❌ ما گدرت أنزله.\n{err}",
    "too_big": "❌ الملف كبير ({size})، الحد {max}.",
    "expired": "انتهت صلاحية هذا الزر، دز الرابط مرة ثانية.",
    "no_history": "ما عندك تنزيلات بعد.",
    "history_title": "آخر تنزيلاتك:",
    "added": "✅ تمت إضافة {uid}", "removed": "✅ تم حذف {uid}", "usage_add": "استخدم: /adduser 123456",
    "owner": "👑 صرت مدير البوت. حتى تضيف أحد من العائلة: خليه يدز /start للبوت، وهو يعطيه رقمه، وانت دز /adduser والرقم.",
    "users": "المسموح لهم:\n{list}", "busy": "⏳ بالدور… ({n} قبلك)",
}

# ------------------------------------------------------------------ database

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, added REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY)")
    con.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER, user_name TEXT, url TEXT, title TEXT, kind TEXT,
                   size INTEGER, status TEXT, error TEXT, time REAL)""")
    return con


def is_admin(uid):
    if uid in ADMIN_IDS:
        return True
    with db() as con:
        return con.execute("SELECT 1 FROM admins WHERE id=?", (uid,)).fetchone() is not None


def claim_admin_if_none(uid):
    """No admin set yet: the first person to send /start becomes the admin (the owner)."""
    if ADMIN_IDS:
        return False
    with db() as con:
        if con.execute("SELECT 1 FROM admins").fetchone():
            return False
        con.execute("INSERT INTO admins (id) VALUES (?)", (uid,))
    return True


def is_allowed(uid):
    if OPEN_TO_ALL or is_admin(uid):
        return True
    with db() as con:
        return con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is not None


def add_history(user, url, title, kind, size, status, error=""):
    with db() as con:
        con.execute("INSERT INTO history (user_id,user_name,url,title,kind,size,status,error,time) VALUES (?,?,?,?,?,?,?,?,?)",
                    (user.id, user.first_name, url, title, kind, size, status, error[:300], time.time()))


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.1f %s" % (n, unit)) if unit != "B" else "%d B" % n
        n /= 1024


# ------------------------------------------------------------------ downloading

PROG_RE = re.compile(r"^DMPROG\s+(\S+)\s+(\S+)\s+(\S+)")


def ytdlp_args(mode, out_dir):
    args = ["yt-dlp", "--newline", "--no-playlist", "--no-colors", "--progress", "--restrict-filenames",
            "-P", str(out_dir), "-o", "%(title).80B [%(id)s].%(ext)s",
            "--progress-template", "download:DMPROG %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s",
            "--max-filesize", str(MAX_BYTES)]
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        args += ["--cookies", COOKIES_FILE]
    if mode == "audio":
        args += ["-x", "--audio-format", "mp3", "--audio-quality", "0", "--embed-thumbnail", "--add-metadata"]
    else:
        # mp4 that plays everywhere (H.264 + AAC preferred), up to 1080p
        args += ["-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
                 "--merge-output-format", "mp4", "-S", "vcodec:h264,res,acodec:m4a"]
    return args


async def run(cmd, on_line=None, timeout=3600):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)
    tail = []
    try:
        async def reader():
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if on_line and on_line(line):
                    continue
                tail.append(line)
                del tail[:-8]
        await asyncio.wait_for(reader(), timeout)
        await proc.wait()
    except asyncio.TimeoutError:
        proc.kill()
        tail.append("Timed out")
    return proc.returncode, tail


def clean_error(tail):
    errs = [l for l in tail if "ERROR" in l or "error" in l.lower()]
    msg = (errs or tail or ["unknown error"])[-1]
    msg = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", msg)
    if "Sign in to confirm" in msg or "not a bot" in msg:
        msg = "يوتيوب طلب تسجيل دخول لهذا السيرفر. يحتاج ملف cookies (شوف الدليل)."
    elif "File is larger than max-filesize" in msg or "larger than max" in msg:
        msg = "الملف أكبر من الحد المسموح."
    elif "Unsupported URL" in msg:
        msg = "هذا الموقع غير مدعوم."
    return msg[:400]


def found_files(out_dir):
    return sorted([p for p in Path(out_dir).rglob("*") if p.is_file() and not p.name.endswith((".part", ".ytdl", ".json"))],
                  key=lambda p: p.stat().st_mtime)


class Job:
    def __init__(self, status_msg):
        self.msg = status_msg
        self.done = self.total = 0
        self.last_edit = 0
        self.last_text = ""

    async def show(self, text, force=False):
        now = time.time()
        if not force and (now - self.last_edit < 3 or text == self.last_text):
            return
        self.last_edit, self.last_text = now, text
        try:
            await self.msg.edit_text(text)
        except TelegramError:
            pass


async def download(url, mode, out_dir, job):
    """Returns (files, error)."""
    loop = asyncio.get_running_loop()

    def on_line(line):
        m = PROG_RE.match(line)
        if not m:
            return False
        def num(x):
            try:
                return float(x)
            except ValueError:
                return 0
        done, total, est = (num(x) for x in m.groups())
        job.done, job.total = done, total or est
        if job.total:
            text = TXT["progress"].format(pct="%d%%" % (100 * job.done / job.total),
                                          done=human(job.done), total=human(job.total))
            loop.create_task(job.show(text))
        return True

    if mode == "photos":
        # gallery-dl handles Pinterest / Instagram / X photo posts; yt-dlp is the fallback
        cmd = ["gallery-dl", "-D", str(out_dir), "--filesize-max", str(MAX_BYTES)]
        if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
            cmd += ["--cookies", COOKIES_FILE]
        code, tail = await run(cmd + [url])
        files = found_files(out_dir)
        if files:
            return files, ""
        mode = "video"

    code, tail = await run(ytdlp_args(mode, out_dir) + [url], on_line)
    files = found_files(out_dir)
    if code == 0 and files:
        return files, ""
    # last try for plain file links: download as-is
    if mode == "video" and not files:
        code2, tail2 = await run(["yt-dlp", "--no-playlist", "--force-generic-extractor", "-P", str(out_dir),
                                  "--max-filesize", str(MAX_BYTES), url])
        files = found_files(out_dir)
        if files:
            return files, ""
    return [], clean_error(tail)


def send_ref(path):
    # In local mode the Telegram server reads the file straight from disk (up to 2 GB)
    return path if LOCAL_MODE else open(path, "rb")


async def send_files(update, files, mode):
    chat = update.effective_chat
    photos = [f for f in files if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    videos = [f for f in files if f.suffix.lower() in (".mp4", ".mov")]
    if mode == "audio":
        for f in [f for f in files if f.suffix.lower() in (".mp3", ".m4a", ".opus", ".ogg")] or files[-1:]:
            await chat.send_chat_action(ChatAction.UPLOAD_VOICE)
            await chat.send_audio(send_ref(f), title=f.stem, read_timeout=600, write_timeout=600)
        return
    if len(files) > 1 and len(photos) + len(videos) == len(files):
        for i in range(0, len(files), 10):
            group = [InputMediaPhoto(send_ref(f)) if f in photos else InputMediaVideo(send_ref(f), supports_streaming=True)
                     for f in files[i:i + 10]]
            await chat.send_media_group(group, read_timeout=600, write_timeout=600)
        return
    for f in files:
        ext = f.suffix.lower()
        if ext in (".mp4", ".mov"):
            await chat.send_chat_action(ChatAction.UPLOAD_VIDEO)
            await chat.send_video(send_ref(f), supports_streaming=True, read_timeout=600, write_timeout=600)
        elif ext in (".jpg", ".jpeg", ".png", ".webp") and f.stat().st_size < 10 * 1024 * 1024:
            await chat.send_photo(send_ref(f), read_timeout=600, write_timeout=600)
        elif ext in (".mp3", ".m4a"):
            await chat.send_audio(send_ref(f), read_timeout=600, write_timeout=600)
        else:
            await chat.send_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await chat.send_document(send_ref(f), read_timeout=600, write_timeout=600)


# ------------------------------------------------------------------ handlers

queue_sem = asyncio.Semaphore(MAX_PARALLEL)
waiting = 0


async def guard(update: Update) -> bool:
    user = update.effective_user
    if user and is_allowed(user.id):
        return True
    if update.effective_message:
        await update.effective_message.reply_html(TXT["not_allowed"].format(uid=user.id if user else "?"))
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if claim_admin_if_none(user.id):
        await update.message.reply_text(TXT["owner"])
    if not await guard(update):
        return
    await update.message.reply_html(TXT["welcome"].format(name=user.first_name, uid=user.id))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    urls = URL_RE.findall(update.message.text or update.message.caption or "")
    if not urls:
        await update.message.reply_html(TXT["welcome"].format(name=update.effective_user.first_name,
                                                              uid=update.effective_user.id))
        return
    for url in urls[:5]:
        key = uuid.uuid4().hex[:10]
        context.bot_data.setdefault("links", {})[key] = url
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(TXT["video"], callback_data="video|" + key),
                                    InlineKeyboardButton(TXT["audio"], callback_data="audio|" + key)],
                                   [InlineKeyboardButton(TXT["photos"], callback_data="photos|" + key)]])
        await update.message.reply_text(TXT["choose"] + "\n" + url, reply_markup=kb,
                                        disable_web_page_preview=True)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting
    q = update.callback_query
    await q.answer()
    if not await guard(update):
        return
    mode, _, key = (q.data or "").partition("|")
    url = context.bot_data.get("links", {}).pop(key, None)
    if not url or mode not in ("video", "audio", "photos"):
        await q.edit_message_text(TXT["expired"])
        return
    user = update.effective_user
    job = Job(q.message)
    if queue_sem.locked():
        await job.show(TXT["busy"].format(n=waiting + 1), force=True)
    waiting += 1
    async with queue_sem:
        waiting -= 1
        await job.show(TXT["working"] + "\n" + url, force=True)
        out_dir = WORK_DIR / uuid.uuid4().hex
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            files, err = await download(url, mode, out_dir, job)
            if not files:
                add_history(user, url, url, mode, 0, "error", err)
                await job.show(TXT["failed"].format(err=err), force=True)
                return
            big = [f for f in files if f.stat().st_size > MAX_BYTES]
            if big:
                size = human(big[0].stat().st_size)
                add_history(user, url, big[0].stem, mode, big[0].stat().st_size, "error", "too big")
                await job.show(TXT["too_big"].format(size=size, max=human(MAX_BYTES)), force=True)
                return
            await job.show(TXT["uploading"], force=True)
            await send_files(update, files, mode)
            total = sum(f.stat().st_size for f in files)
            title = re.sub(r"\s*\[[^\]]+\]$", "", files[0].stem).replace("_", " ")
            add_history(user, url, title, mode, total, "done")
            try:
                await q.message.delete()
            except TelegramError:
                pass
        except Exception as e:  # keep the bot alive whatever happens
            log.exception("job failed")
            add_history(user, url, url, mode, 0, "error", str(e))
            await job.show(TXT["failed"].format(err=str(e)[:300]), force=True)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    with db() as con:
        rows = con.execute("SELECT title,url,kind,size,status,time FROM history WHERE user_id=? ORDER BY id DESC LIMIT 15",
                           (update.effective_user.id,)).fetchall()
    if not rows:
        await update.message.reply_text(TXT["no_history"])
        return
    icon = {"video": "🎬", "audio": "🎵", "photos": "🖼"}
    lines = [TXT["history_title"]]
    for title, url, kind, size, status, t in rows:
        mark = "✅" if status == "done" else "❌"
        lines.append("%s %s %s\n%s · %s\n%s" % (mark, icon.get(kind, "📦"), title[:60],
                                               time.strftime("%Y-%m-%d %H:%M", time.localtime(t)),
                                               human(size) if size else "-", url))
    await update.message.reply_text("\n\n".join(lines), disable_web_page_preview=True)


async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ids = [int(a) for a in context.args if a.isdigit()]
    if not ids:
        await update.message.reply_text(TXT["usage_add"])
        return
    with db() as con:
        for uid in ids:
            con.execute("INSERT OR IGNORE INTO users (id, added) VALUES (?, ?)", (uid, time.time()))
    await update.message.reply_text(TXT["added"].format(uid=", ".join(map(str, ids))))


async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ids = [int(a) for a in context.args if a.isdigit()]
    with db() as con:
        for uid in ids:
            con.execute("DELETE FROM users WHERE id=?", (uid,))
    await update.message.reply_text(TXT["removed"].format(uid=", ".join(map(str, ids))))


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db() as con:
        ids = [str(r[0]) for r in con.execute("SELECT id FROM users")]
    await update.message.reply_text(TXT["users"].format(list="\n".join(ids) or "-"))


async def update_ytdlp(context: ContextTypes.DEFAULT_TYPE):
    # video sites change often; keep yt-dlp and gallery-dl fresh
    code, tail = await run(["pip", "install", "-q", "-U", "yt-dlp[default]", "gallery-dl"], timeout=600)
    log.info("yt-dlp update finished (%s)", code)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.warning("update failed: %s", context.error)


def main():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    db().close()
    builder = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True)
    if LOCAL_MODE:
        builder = builder.base_url(API_BASE + "/bot").base_file_url(API_BASE + "/file/bot").local_mode(True)
    builder = builder.read_timeout(60).write_timeout(600).connect_timeout(30).media_write_timeout(600)
    app: Application = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_text))
    app.add_error_handler(on_error)
    if app.job_queue:
        app.job_queue.run_repeating(update_ytdlp, interval=24 * 3600, first=10)
    log.info("Bot started (local server: %s, max file %s)", LOCAL_MODE, human(MAX_BYTES))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
