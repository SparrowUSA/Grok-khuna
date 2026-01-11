import os
import sys
import asyncio
import logging

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check environment
SESSION = os.getenv("SESSION_STRING")
if not SESSION:
    logger.error("ERROR: Add SESSION_STRING to Railway Variables!")
    sys.exit(1)

# Try to import - will fail if not installed
try:
    from pyrogram import Client, filters
    from pyrogram.types import Message
    print("✓ Pyrogram imported successfully")
except ImportError as e:
    logger.error(f"Pyrogram not installed: {e}")
    sys.exit(1)

# Create client
app = Client(
    "railway_bot",
    session_string=SESSION,
    api_id=int(os.getenv("API_ID", "0")),
    api_hash=os.getenv("API_HASH", ""),
    in_memory=True
)

# Simple command
@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply("🏓 Pong! Bot is alive.")

# Main
async def main():
    await app.start()
    me = await app.get_me()
    logger.info(f"✅ Bot started as @{me.username}")
    await app.send_message("me", f"🤖 Bot started: @{me.username}")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
