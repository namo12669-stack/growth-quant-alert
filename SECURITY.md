# Security and data handling

Keep this repository and its artifacts private for personal research. Do not commit tokens,
chat IDs, downloaded market data, local state, or financial account details. There is no broker
integration and no reason to provide broker credentials to this project.

Use a new dedicated Telegram bot. Store the token and chat ID in repository Actions secrets.
The setup helper sends the chat ID only to a uniquely identified private chat and refuses an
existing webhook. Rotate any exposed bot token through BotFather.

Network requests occur only to the configured market-data adapter, Telegram Bot API and
GitHub artifact API. Dependencies have their own upstream behavior and data terms. Review
updates before merging. Action version tags and dependency version ranges are not a cryptographic
supply-chain lock; pin reviewed action SHAs and a tested dependency lock for stronger assurance.

No token-bearing Telegram request exception is printed. CSV string fields are neutralized
against spreadsheet-formula interpretation. GitHub summaries use escaped code blocks. Artifact
extraction rejects traversal/unexpected file types and oversized uncompressed archives.

Exactly-once Telegram delivery and durable state are not guaranteed. Artifact restoration
errors stop scanning. Deleting or expiring artifacts resets history. A private repository still
requires least-privilege collaborator access and control of the bot account.
