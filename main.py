import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from yt_dlp import YoutubeDL

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
MAX_SIZE = 50 * 1024 * 1024  # Telegram bot limiti: 50 MB
FFMPEG_PATH = str(Path(__file__).parent / "bin" / "ffmpeg.exe")
DOWNLOAD_DIR = Path(__file__).parent / "downloads"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

SUPPORTED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "fb.com",
    "pinterest.com",
    "pin.it",
)


def is_supported(url: str) -> bool:
    return any(domain in url.lower() for domain in SUPPORTED_DOMAINS)


def get_ydl_opts(download_dir: str) -> dict:
    return {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(download_dir, "%(id)s.%(ext)s"),
        "ffmpeg_location": FFMPEG_PATH,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "retries": 3,
        "socket_timeout": 30,
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Assalomu alaykum! 👋\n\n"
        "Men video yuklovchi botman. Menga quyidagi saytlardan video "
        "yoki post havolasini yuboring:\n\n"
        "• Instagram\n"
        "• YouTube\n"
        "• Facebook\n"
        "• Pinterest\n\n"
        "Misol: https://www.instagram.com/reel/...\n"
        "https://www.youtube.com/watch?v=..."
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Botdan foydalanish:\n\n"
        "1. Video yuklamoqchi bo'lgan post havolasini nusxalang\n"
        "2. Shu yerda botga yuboring\n"
        "3. Bot videoni yuklab, sizga qaytaradi\n\n"
        "Eslatma: Telegram botlari uchun maksimal fayl hajmi 50 MB."
    )


def get_files_in_dir(directory: str) -> list[str]:
    files = []
    for f in os.listdir(directory):
        filepath = os.path.join(directory, f)
        if os.path.isfile(filepath):
            files.append(filepath)
    return files


def cleanup_directory(directory: str) -> None:
    for f in get_files_in_dir(directory):
        try:
            os.remove(f)
        except OSError:
            pass


async def download_video(url: str, update: Update) -> str | None:
    download_dir = tempfile.mkdtemp(prefix="video_dl_")
    opts = get_ydl_opts(download_dir)

    try:
        await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        files = get_files_in_dir(download_dir)
        if not files:
            return None

        filepath = files[0]
        size = os.path.getsize(filepath)
        if size > MAX_SIZE:
            title = info.get("title", "video")
            cleanup_directory(download_dir)
            os.rmdir(download_dir)
            return f"⚠️ Kechirasiz, video juda katta ({size / 1024 / 1024:.1f} MB). Telegram limiti 50 MB."

        return filepath
    except Exception as e:
        logger.error("Download error: %s", e)
        cleanup_directory(download_dir)
        try:
            os.rmdir(download_dir)
        except OSError:
            pass
        return None


async def send_result(update: Update, filepath: str) -> None:
    title = Path(filepath).stem
    with open(filepath, "rb") as f:
        await update.message.reply_video(
            video=f,
            caption=f"📥 Yuklab olindi: {title}",
            supports_streaming=True,
        )
    os.remove(filepath)
    parent = os.path.dirname(filepath)
    try:
        os.rmdir(parent)
    except OSError:
        pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or update.message.caption or ""
    url_match = URL_REGEX.search(text)

    if not url_match:
        await update.message.reply_text(
            "⚠️ Havola topilmadi. Video/post havolasini yuboring."
        )
        return

    url = url_match.group(0).rstrip(".,;!?")
    if not is_supported(url):
        await update.message.reply_text(
            "⚠️ Bu sayt qo'llab-quvvatlanmaydi. Faqat Instagram, YouTube, "
            "Facebook va Pinterest havolalarini yuboring."
        )
        return

    status_msg = await update.message.reply_text("⏳ Video yuklanmoqda, biroz kuting...")

    result = await download_video(url, update)

    if result is None:
        await status_msg.edit_text(
            "❌ Videoni yuklab bo'lmadi. Sabablari:\n"
            "• Post shaxsiy (private) bo'lishi mumkin\n"
            "• Havola noto'g'ri bo'lishi mumkin\n"
            "• Sayt botni bloklagan bo'lishi mumkin\n\n"
            "Iltimos, boshqa havola bilan urinib ko'ring."
        )
    elif result.startswith("⚠️"):
        await status_msg.edit_text(result)
    else:
        await status_msg.delete()
        try:
            await send_result(update, result)
        except Exception as e:
            logger.error("Send error: %s", e)
            await update.message.reply_text("❌ Faylni yuborishda xatolik yuz berdi.")


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
