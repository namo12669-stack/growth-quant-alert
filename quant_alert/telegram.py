from __future__ import annotations

import os
import time
from typing import Callable

import requests


class TelegramError(RuntimeError):
    """A redacted error: never includes the token-bearing request URL."""


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def split_messages(text: str, limit: int = 3800) -> list[str]:
    if limit < 2:
        raise ValueError("Message limit is too small")
    messages, current = [], ""
    for line in text.splitlines(keepends=True):
        if utf16_length(current + line) <= limit:
            current += line
            continue
        if current:
            messages.append(current.rstrip())
            current = ""
        for char in line:
            if utf16_length(current + char) > limit:
                messages.append(current.rstrip())
                current = ""
            current += char
    if current.strip():
        messages.append(current.rstrip())
    return messages


class TelegramClient:
    def __init__(self, token: str, chat_id: str | None = None, session=None,
                 sleep: Callable[[float], None] = time.sleep):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip() if chat_id is not None else None
        self.session = session or requests.Session()
        self.sleep = sleep
        if not self.token or ":" not in self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is missing or malformed")

    @classmethod
    def from_env(cls, require_chat: bool = True):
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if require_chat and not chat:
            raise TelegramError("Add TELEGRAM_CHAT_ID to repository Actions secrets")
        return cls(os.getenv("TELEGRAM_BOT_TOKEN", ""), chat or None)

    def call(self, method: str, payload: dict) -> dict | list:
        for attempt in range(3):
            try:
                response = self.session.post(
                    f"https://api.telegram.org/bot{self.token}/{method}",
                    json=payload, timeout=(10, 30))
                body = response.json()
            except (requests.RequestException, ValueError):
                # A timed-out send may already have been accepted. Do not blindly
                # retry an uncertain sendMessage delivery and create duplicates.
                raise TelegramError("Telegram connection/response failed; delivery status may be unknown") from None
            if response.status_code == 429 and attempt < 2:
                retry = min(60, max(1, int(body.get("parameters", {}).get("retry_after", 2))))
                self.sleep(retry)
                continue
            if response.status_code >= 500 and attempt < 2 and method != "sendMessage":
                self.sleep(2 ** attempt)
                continue
            if not body.get("ok"):
                code = body.get("error_code", response.status_code)
                hints = {400: "Check chat ID, /start, or existing webhook", 401: "Check BotFather token",
                         403: "Bot blocked, not started, or lacks chat access", 409: "Another poller or webhook is active"}
                raise TelegramError(f"Telegram rejected request ({code}). {hints.get(code, 'Try again after checking Telegram status')}")
            return body.get("result", {})
        raise TelegramError("Telegram rate limit persisted")

    def send(self, text: str, chat_id: str | None = None) -> list[int]:
        target = chat_id or self.chat_id
        if not target:
            raise TelegramError("Missing Telegram chat ID")
        ids = []
        for message in split_messages(text):
            result = self.call("sendMessage", {"chat_id": target, "text": message,
                                                "link_preview_options": {"is_disabled": True}})
            ids.append(result["message_id"])
        return ids
