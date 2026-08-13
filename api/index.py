import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import MAX_FILE_SIZE, SUPPORTED_RE, URL_REGEX, cleanup, download_video

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_PATH = "/api/webhook"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

telegram_app = Application.builder().token(TOKEN).build()
bot = telegram_app.bot

START_TEXT = (
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or update.message.caption or ""
    url_match = URL_REGEX.search(text)

    if not url_match:
        await update.message.reply_text("⚠️ Havola topilmadi. Video/post havolasini yuboring.")
        return

    url = url_match.group(0).rstrip(".,;!?")
    if not SUPPORTED_RE.search(url):
        await update.message.reply_text(
            "⚠️ Bu sayt qo'llab-quvvatlanmaydi. Faqat Instagram, YouTube, "
            "Facebook va Pinterest havolalarini yuboring."
        )
        return

    status_msg = await update.message.reply_text("⏳ Video yuklanmoqda, biroz kuting...")
    loop = asyncio.get_running_loop()
    path = None
    try:
        path = await loop.run_in_executor(None, download_video, url)
        size = os.path.getsize(path)
        if size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"⚠️ Kechirasiz, video juda katta ({size / 1024 / 1024:.1f} MB). "
                "Telegram limiti 50 MB."
            )
            return

        await update.message.chat.send_action(ChatAction.UPLOAD_VIDEO)
        with open(path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="✅ Mana videongiz!",
                supports_streaming=True,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error("Download error: %s", e)
        await status_msg.edit_text(
            "❌ Videoni yuklab bo'lmadi. Sabablari:\n"
            "• Post shaxsiy (private) bo'lishi mumkin\n"
            "• Havola noto'g'ri bo'lishi mumkin\n"
            "• Sayt botni bloklagan bo'lishi mumkin\n\n"
            "Iltimos, boshqa havola bilan urinib ko'ring."
        )
    finally:
        if path:
            await loop.run_in_executor(None, cleanup, path)


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    url = os.getenv("WEBHOOK_URL") or f"https://{os.getenv('VERCEL_PROJECT_PRODUCTION_URL')}{WEBHOOK_PATH}"
    await bot.set_webhook(url)
    logger.info("Webhook set: %s", url)
    yield
    await telegram_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return {"status": "ok", "bot": "video downloader"}


@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    await telegram_app.initialize()
    await telegram_app.process_update(update)
    return {"ok": True}