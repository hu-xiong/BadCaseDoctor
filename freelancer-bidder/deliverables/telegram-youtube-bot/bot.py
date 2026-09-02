"""
Telegram YouTube Downloader Bot
Bid project: Python Telegram Bot Development Needed

Features:
  - Multi-language UI (EN / ZH / RU / ES)
  - Paste YouTube URL -> choose Video / Audio (MP3)
  - yt-dlp download + Telegram send
  - File size guard (Telegram Bot API ~50MB soft limit)

Setup:
  1. Create bot via @BotFather, copy token
  2. copy .env.example -> .env and set BOT_TOKEN
  3. pip install -r requirements.txt
  4. Optional: install ffmpeg on PATH for audio merge
  5. python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAX_MB = float(os.getenv("MAX_FILE_MB", "48"))
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("yt-bot")

URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/\S+",
    re.I,
)

I18N = {
    "en": {
        "start": (
            "Send a YouTube link.\n"
            "Commands: /lang en|zh|ru|es\n"
            "I will ask Video or Audio (MP3)."
        ),
        "ask_mode": "Choose download type for:\n{title}",
        "video": "🎬 Video",
        "audio": "🎵 Audio (MP3)",
        "working": "Downloading… please wait.",
        "too_big": "File is ~{size:.1f} MB (limit {limit:.0f} MB). Try a shorter video or audio.",
        "bad_url": "Please send a valid YouTube URL.",
        "done": "Done.",
        "fail": "Download failed: {err}",
        "lang_set": "Language set to English.",
        "need_token": "BOT_TOKEN missing. Set it in .env",
    },
    "zh": {
        "start": "发送 YouTube 链接。\n命令: /lang en|zh|ru|es\n可选择视频或音频(MP3)。",
        "ask_mode": "请选择下载类型：\n{title}",
        "video": "🎬 视频",
        "audio": "🎵 音频 (MP3)",
        "working": "正在下载，请稍候…",
        "too_big": "文件约 {size:.1f} MB（上限 {limit:.0f} MB）。请换更短视频或音频。",
        "bad_url": "请发送有效的 YouTube 链接。",
        "done": "完成。",
        "fail": "下载失败：{err}",
        "lang_set": "语言已设为中文。",
        "need_token": "缺少 BOT_TOKEN，请在 .env 中配置",
    },
    "ru": {
        "start": "Отправьте ссылку YouTube.\nКоманды: /lang en|zh|ru|es",
        "ask_mode": "Выберите тип загрузки:\n{title}",
        "video": "🎬 Видео",
        "audio": "🎵 Аудио (MP3)",
        "working": "Скачиваю…",
        "too_big": "Файл ~{size:.1f} МБ (лимит {limit:.0f} МБ).",
        "bad_url": "Нужна корректная ссылка YouTube.",
        "done": "Готово.",
        "fail": "Ошибка: {err}",
        "lang_set": "Язык: русский.",
        "need_token": "Нет BOT_TOKEN в .env",
    },
    "es": {
        "start": "Envía un enlace de YouTube.\nComandos: /lang en|zh|ru|es",
        "ask_mode": "Elige el tipo de descarga:\n{title}",
        "video": "🎬 Vídeo",
        "audio": "🎵 Audio (MP3)",
        "working": "Descargando…",
        "too_big": "Archivo ~{size:.1f} MB (límite {limit:.0f} MB).",
        "bad_url": "Envía una URL de YouTube válida.",
        "done": "Listo.",
        "fail": "Error: {err}",
        "lang_set": "Idioma: español.",
        "need_token": "Falta BOT_TOKEN en .env",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    pack = I18N.get(lang) or I18N["en"]
    text = pack.get(key) or I18N["en"][key]
    return text.format(**kwargs) if kwargs else text


def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang") or DEFAULT_LANG


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    if not m:
        return None
    url = m.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    return url


def probe_title(url: str) -> str:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return (info or {}).get("title") or url


def download_media(url: str, mode: str, workdir: Path) -> Path:
    import yt_dlp

    outtmpl = str(workdir / "%(title).80B [%(id)s].%(ext)s")
    if mode == "audio":
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
    else:
        opts = {
            "format": "bv*[height<=720]+ba/b[height<=720]/b",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
        if mode == "audio":
            path = path.with_suffix(".mp3")
        if not path.exists():
            # yt-dlp may sanitize filename; pick newest file
            files = sorted(workdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                raise FileNotFoundError("download produced no file")
            path = files[0]
        return path


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    await update.message.reply_text(t(lang, "start"))


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() not in I18N:
        await update.message.reply_text("Usage: /lang en|zh|ru|es")
        return
    lang = context.args[0].lower()
    context.user_data["lang"] = lang
    await update.message.reply_text(t(lang, "lang_set"))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    url = extract_url(update.message.text or "")
    if not url:
        await update.message.reply_text(t(lang, "bad_url"))
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        title = await asyncio.to_thread(probe_title, url)
    except Exception as exc:
        await update.message.reply_text(t(lang, "fail", err=str(exc)[:300]))
        return

    context.user_data["pending_url"] = url
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t(lang, "video"), callback_data="dl:video"),
                InlineKeyboardButton(t(lang, "audio"), callback_data="dl:audio"),
            ]
        ]
    )
    await update.message.reply_text(t(lang, "ask_mode", title=title[:200]), reply_markup=keyboard)


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text(t(lang, "bad_url"))
        return

    mode = "audio" if query.data.endswith("audio") else "video"
    await query.edit_message_text(t(lang, "working"))
    await context.bot.send_chat_action(
        update.effective_chat.id,
        ChatAction.UPLOAD_DOCUMENT if mode == "audio" else ChatAction.UPLOAD_VIDEO,
    )

    workdir = Path(tempfile.mkdtemp(prefix="ytbot_"))
    try:
        path = await asyncio.to_thread(download_media, url, mode, workdir)
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_MB:
            await query.message.reply_text(t(lang, "too_big", size=size_mb, limit=MAX_MB))
            return

        with path.open("rb") as f:
            if mode == "audio":
                await query.message.reply_audio(audio=f, filename=path.name)
            else:
                await query.message.reply_video(video=f, filename=path.name, supports_streaming=True)
        await query.message.reply_text(t(lang, "done"))
    except Exception as exc:
        log.exception("download failed")
        await query.message.reply_text(t(lang, "fail", err=str(exc)[:400]))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        context.user_data.pop("pending_url", None)


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit(I18N["en"]["need_token"])

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CallbackQueryHandler(on_choice, pattern=r"^dl:(video|audio)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
