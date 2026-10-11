import asyncio
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import re
from aioimaplib import aioimaplib
from aiogram import Bot
from bs4 import BeautifulSoup
from sqlalchemy import select

from config import settings
from database import ProcessedEmail, async_session


def decode_str(val: str | None) -> str:
    if not val:
        return ""
    res = ""
    for part, enc in decode_header(val):
        if isinstance(part, bytes):
            res += part.decode(enc or "utf-8", errors="replace")
        else:
            res += str(part)
    return res


def clean_avito_html(raw_content: str) -> dict:
    if not raw_content:
        return {}

    soup = BeautifulSoup(raw_content, "html.parser")
    for tag in soup(["script", "style", "img", "header", "footer"]):
        tag.decompose()
    for tag in soup.find_all(["br", "p", "div", "tr", "li"]):
        tag.insert_after("\n")
    text = soup.get_text()

    stop_markers = [
        r"Ответить",
        r"Отключить уведомления",
        r"Вы получили это письмо",
        r"Установить мобильное приложение",
        r"Если у вас возникли вопросы",
    ]
    for pattern in stop_markers:
        parts = re.split(pattern, text, flags=re.IGNORECASE)
        if len(parts) > 1:
            text = parts[0]

    lines = [
        re.sub(r"^[<>\s\-—]+|[<>\s\-—]+$", "", l).strip()
        for l in text.splitlines()
        if l.strip()
    ]
    item, author, msg_lines = "", "", []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lower().startswith("объявление"):
            item = re.sub(
                r"^объявление\s*", "", line, flags=re.IGNORECASE
            ).strip()
            if i + 1 < len(lines):
                author = lines[i + 1]
                i += 2
                continue
            i += 1
            continue
        msg_lines.append(line)
        i += 1

    return {
        "item": item,
        "author": author or "Покупатель",
        "message": "\n".join(msg_lines).strip() or "(текст не найден)",
    }


async def mail_worker(bot: Bot):
    if (
        not settings.GMAIL_USER
        or not settings.GMAIL_APP_PASSWORD.get_secret_value()
    ):
        return

    while True:
        try:
            imap = aioimaplib.IMAP4_SSL(host=settings.IMAP_SERVER)
            await imap.wait_hello_from_server()
            await imap.login(
                settings.GMAIL_USER,
                settings.GMAIL_APP_PASSWORD.get_secret_value(),
            )
            await imap.select("INBOX")

            status, data = await imap.search('FROM "messages@avito.ru"')
            if status == "OK" and data[0]:
                uids = data[0].split()[-15:]
                async with async_session() as session:
                    for uid_b in uids:
                        uid_str = uid_b.decode()
                        exists = await session.execute(
                            select(ProcessedEmail).where(
                                ProcessedEmail.email_uid == uid_str
                            )
                        )
                        if exists.scalar_one_or_none():
                            continue

                        _, msg_data = await imap.fetch(uid_str, "(RFC822)")
                        raw_msg = email.message_from_bytes(msg_data[1])
                        subject = decode_str(raw_msg.get("Subject"))
                        raw_date = raw_msg.get("Date", "")
                        try:
                            date_str = parsedate_to_datetime(raw_date).strftime(
                                "%d.%m.%Y %H:%M"
                            )
                        except Exception:
                            date_str = raw_date

                        payload = ""
                        if raw_msg.is_multipart():
                            for part in raw_msg.walk():
                                if part.get_content_type() in (
                                    "text/html",
                                    "text/plain",
                                ):
                                    data_bytes = part.get_payload(decode=True)
                                    if data_bytes:
                                        payload = data_bytes.decode(
                                            "utf-8", errors="replace"
                                        )
                                        break
                        else:
                            data_bytes = raw_msg.get_payload(decode=True)
                            if data_bytes:
                                payload = data_bytes.decode(
                                    "utf-8", errors="replace"
                                )

                        parsed = clean_avito_html(payload)
                        msg_text = (
                            f"💬 <b>Новое сообщение на Avito</b>\n"
                            f"📦 Товар: <b>{parsed.get('item') or subject}</b>\n"
                            f"👤 От кого: <b>{parsed.get('author')}</b>\n"
                            f"🕒 Время: <code>{date_str}</code>\n\n"
                            f"Текст:\n{parsed.get('message')}"
                        )

                        await bot.send_message(
                            settings.ADMIN_ID,
                            msg_text[:4000],
                            parse_mode="HTML",
                        )
                        session.add(ProcessedEmail(email_uid=uid_str))
                        await session.commit()

            await imap.logout()
        except Exception:
            pass

        await asyncio.sleep(settings.CHECK_INTERVAL)
