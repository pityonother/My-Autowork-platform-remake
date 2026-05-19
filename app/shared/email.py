from __future__ import annotations

import html
import re
from email.message import EmailMessage, Message


def safe_attachment_name(filename: str | None, fallback: str = "attachment") -> str:
    name = str(filename or fallback).replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    return name or fallback


def html_to_plain_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value)
    text = re.sub(r"(?is)<style.*?</style>|<script.*?</script>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", text)).strip()


def iter_message_attachments(message: Message | EmailMessage):
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            yield part
