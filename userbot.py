#!/usr/bin/env python3
"""
Ultra-minimal Telegram UserBot for Railway - Fast Deployment
"""

import os
import sys

# Check and install dependencies
def ensure_package(package):
    try:
        __import__(package.replace('-', '_'))
        print(f"✓ {package}")
        return True
    except ImportError:
        print(f"📦 Installing {package}...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", package])
            print(f"✓ {package} installed")
            return True
        except:
            print(f"✗ Failed to install {package}")
            return False

# Only install if missing
ensure_package("pyrogram")
ensure_package("tgcrypto")

# Now import
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Get config
SESSION = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")

if not SESSION:
    logger.error("❌ Add SESSION_STRING to Railway Variables!")
    sys.exit(1)

# Create client
app = Client(
    "railway_bot",
    session_string=SESSION,
    api_id=int(API_ID) if API_ID.isdigit() else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True
)

# Simple ping command
@app.on_message(filters.command("ping") & filters.private)
async def ping(client: Client, message: Message):
    await message.reply("🏓 Pong! Bot is alive.")

# Forward command (your main function)
@app.on_message(filters.command("forward") & filters.me)
async def forward_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /forward https://t.me/c/xxx/123")
        return
    
    await message.reply("✅ Forward command received! (Minimal version running)")

# Main
async def main():
    await app.start()
    user = await app.get_me()
    logger.info(f"✅ Bot started as @{user.username}")
    
    # Simple startup message
    await app.send_message("me", "🤖 Minimal Bot Started on Railway!")
    
    # Keep alive
    try:
        # Create a simple health check that doesn't need aiohttp
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
