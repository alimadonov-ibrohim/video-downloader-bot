import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import MAX_FILE_SIZE, SUPPORTED_RE, URL_REGEX, cleanup, download_video

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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

HELP_TEXT = (
    "Botdan foydalanish:\n\n"
    "1. Video yuklamoqchi bo'lgan post havolasini nusxalang\n"
    "2. Shu yerda botga yuboring\n"
    "3. Bot videoni yuklab, sizga qaytaradi\n\n"
    "Eslatma: Telegram botlari uchun maksimal fayl hajmi 50 MB."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


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
        logger.error("Download error: %s", e, exc_info=True)
        await status_msg.edit_text(
            "❌ Videoni yuklab bo'lmadi.\n\n"
            f"🔧 Texnik xato: {type(e).__name__}: {e}\n\n"
            "Iltimos, boshqa havola bilan urinib ko'ring."
        )
    finally:
        if path:
            await loop.run_in_executor(None, cleanup, path)


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()