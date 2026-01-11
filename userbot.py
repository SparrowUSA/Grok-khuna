import os
import sys
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get credentials
SESSION = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not SESSION:
    logger.error("Add SESSION_STRING to Railway Variables!")
    sys.exit(1)

# Create client
app = Client(
    "railway_bot",
    session_string=SESSION,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True
)

# Command handlers
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    await message.reply("✅ Bot is running on Railway!")

@app.on_message(filters.command("forward") & filters.me)
async def forward_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /forward https://t.me/c/xxx/123")
        return
    await message.reply("📥 Processing... (Add your forwarding logic here)")

# Main function
async def main():
    await app.start()
    me = await app.get_me()
    logger.info(f"Bot started: @{me.username}")
    await app.send_message("me", f"🤖 Bot online! @{me.username}")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
