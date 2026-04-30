"""Telegram bot entry point. Run with: python bot.py"""
import asyncio
import logging
import os
import threading
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pipeline import cleanup_job, run_job
from translator import parse_chapters_arg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Xin chào! Gửi lệnh sau để dịch tiểu thuyết:\n\n"
        "/translate <url> [chương]\n\n"
        "Ví dụ:\n"
        "/translate https://truyenfull.vision/ten-truyen/\n"
        "/translate https://truyenfull.vision/ten-truyen/ 1-50\n"
        "/translate https://truyenfull.vision/ten-truyen/ 1,3,5\n\n"
        "Hỗ trợ: truyenfull.vision, zingtruyen.store"
    )


async def cmd_translate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Vui lòng cung cấp URL. Ví dụ:\n/translate https://truyenfull.vision/ten-truyen/"
        )
        return

    book_url = context.args[0].strip()
    chapter_filter = parse_chapters_arg(context.args[1]) if len(context.args) > 1 else None
    chat_id = update.effective_chat.id
    filter_note = f" (chương {context.args[1]})" if chapter_filter is not None else ""
    await update.message.reply_text(
        f"Đã nhận yêu cầu:\n{book_url}{filter_note}\n\nTôi sẽ thông báo khi hoàn thành."
    )
    logger.info("Received translation request: %s%s", book_url, filter_note)

    loop = asyncio.get_event_loop()

    def run() -> None:
        _MILESTONES = {"Found", "Scraped", "Translated", "Combining", "EPUB", "Done", "Lỗi", "FAILED"}

        def send(msg: str) -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(chat_id=chat_id, text=msg), loop
                ).result(timeout=30)
            except Exception as exc:
                logger.warning("Could not send Telegram message: %s", exc)

        def progress_cb(msg: str) -> None:
            logger.info("[job] %s", msg)
            if any(kw in msg for kw in _MILESTONES):
                send(msg)

        try:
            epub_path = run_job(book_url, progress_cb=progress_cb, chapter_filter=chapter_filter)
            with open(epub_path, "rb") as fh:
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_document(
                        chat_id=chat_id,
                        document=fh,
                        filename=epub_path.name,
                        caption="Dịch hoàn tất!",
                    ),
                    loop,
                ).result(timeout=120)
            cleanup_job(epub_path)
        except Exception as e:
            logger.exception("Job failed for %s", book_url)
            send(f"Lỗi: {e}")

    threading.Thread(target=run, daemon=True).start()


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("translate", cmd_translate))
    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
