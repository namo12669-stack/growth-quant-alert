"""Run manually after sending /start to your own bot. Never prints bot tokens."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from growth_alert.telegram import TelegramClient, TelegramError


def main() -> int:
    client = TelegramClient.from_env(require_chat=False)
    me = client.call("getMe", {})
    print(f"Connected to bot @{me.get('username', 'unknown')}")
    webhook = client.call("getWebhookInfo", {})
    if webhook.get("url"):
        raise TelegramError("This bot already has a webhook. Create a separate bot; do not disconnect an existing service")
    updates = client.call("getUpdates", {"timeout": 0, "limit": 100, "allowed_updates": ["message"]})
    private = {}
    for update in updates:
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        if chat.get("type") == "private":
            private[str(chat["id"])] = chat
    if len(private) != 1:
        raise TelegramError("Expected one private chat. Send /start to your NEW bot and retry. Use a dedicated bot, not a shared one")
    chat_id = next(iter(private))
    client.send("Growth Alert setup connected.\n\nYour TELEGRAM_CHAT_ID is:\n" + chat_id +
                "\n\nAdd this value as the TELEGRAM_CHAT_ID repository Actions secret. "
                "Then run Growth Alerts in demo mode.", chat_id=chat_id)
    print("Chat ID was sent privately to your Telegram, not printed in this log.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TelegramError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
