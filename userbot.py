# userbot.py - Optimized for Railway deployment
import os
import asyncio
import logging
import signal
import time
from urllib.parse import urlparse
from pyrogram import Client, filters, errors, idle
from pyrogram.types import Message
from aiohttp import web

# ─── LOGGING SETUP ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("pyrogram")
logger.setLevel(logging.INFO)

# ─── CONFIG FROM RAILWAY ENV ──────────────────────────────────────────────
SESSION_STRING = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", 8080))  # Railway provides PORT
HEALTH_CHECK_PATH = os.getenv("HEALTH_CHECK_PATH", "/health")

if not SESSION_STRING:
    raise ValueError("SESSION_STRING is required! Add it in Railway Variables.")

# ─── CLIENT INIT ───────────────────────────────────────────────────────────
app = Client(
    name="restricted_forwarder",
    session_string=SESSION_STRING,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True,  # Important for Railway to avoid file system issues
)

# ─── HEALTH CHECK SERVER (Required for Railway) ───────────────────────────
async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Start a simple HTTP server for Railway health checks"""
    server = web.Application()
    server.router.add_get(HEALTH_CHECK_PATH, health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Health check server running on port {PORT}")
    return runner

# ─── UTILITIES ──────────────────────────────────────────────────────────────

def parse_tg_link(link: str) -> tuple[int, int]:
    parsed = urlparse(link)
    path = parsed.path.strip('/').split('/')
    if len(path) != 3 or path[0] != 'c':
        raise ValueError("Invalid link! Example: https://t.me/c/123456789/100")
    channel_id = int(f"-100{path[1]}")
    msg_id = int(path[2])
    return channel_id, msg_id


async def progress_callback(current: int, total: int):
    if total > 0 and current % (total // 10) < 1:  # ~every 10%
        logger.info(f"Progress: {current * 100 / total:.1f}%")


async def process_message(client: Client, channel_id: int, msg_id: int):
    try:
        msg = await client.get_messages(channel_id, msg_id)
        if not msg:
            await client.send_message("me", f"✗ Message {msg_id} not found")
            return

        logger.info(f"Processing message {msg_id} - type: {msg.media}")

        # Text
        if msg.text:
            await client.send_message("me", msg.text)

        # Media (video/document/photo)
        elif msg.media:
            file_path = await client.download_media(
                msg,
                progress=progress_callback
            )

            if msg.video:
                await client.send_video(
                    "me",
                    file_path,
                    caption=msg.caption,
                    supports_streaming=True,
                    progress=progress_callback
                )
            elif msg.document:
                await client.send_document(
                    "me",
                    file_path,
                    caption=msg.caption,
                    progress=progress_callback
                )
            elif msg.photo:
                await client.send_photo("me", file_path, caption=msg.caption)
            else:
                await client.send_message("me", f"Skipped {msg_id} - unsupported media")

            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")

        else:
            await client.send_message("me", f"Skipped {msg_id} - no content")

    except errors.FloodWait as fw:
        logger.warning(f"FloodWait: waiting {fw.value} seconds")
        await asyncio.sleep(fw.value)
        await process_message(client, channel_id, msg_id)  # retry
    except Exception as e:
        logger.error(f"Error on {msg_id}: {type(e).__name__} - {e}")
        await client.send_message("me", f"Error {msg_id}: {str(e)}")


# ─── COMMAND HANDLERS ───────────────────────────────────────────────────────

@app.on_message(filters.command("forward", prefixes="/") & filters.me)
async def single_forward(client: Client, message: Message):
    logger.info(f"/forward triggered by {message.from_user.id}")
    if len(message.command) < 2:
        return await message.reply("Usage: /forward https://t.me/c/xxxx/123")

    try:
        channel_id, msg_id = parse_tg_link(message.command[1])
        await message.reply(f"→ Processing {msg_id}...")
        await process_message(client, channel_id, msg_id)
        await message.reply("✓ Done!")
    except Exception as e:
        await message.reply(f"Error: {str(e)}")


@app.on_message(filters.command("batch", prefixes="/") & filters.me)
async def batch_forward(client: Client, message: Message):
    logger.info(f"/batch triggered")
    if len(message.command) < 3:
        return await message.reply("Usage: /batch start_link end_link")

    try:
        start_ch, start_id = parse_tg_link(message.command[1])
        end_ch, end_id = parse_tg_link(message.command[2])
        if start_ch != end_ch:
            return await message.reply("Both links must be from same channel")

        await message.reply(f"Batch {start_id} → {end_id} started...")
        count = 0
        for mid in range(start_id, end_id + 1):
            await process_message(client, start_ch, mid)
            count += 1
            await asyncio.sleep(1.2)  # anti-flood

        await message.reply(f"Batch complete • {count} messages")
    except Exception as e:
        await message.reply(f"Batch failed: {str(e)}")


# ─── START ──────────────────────────────────────────────────────────────────

async def main():
    # Start health check server first
    health_server = await start_health_server()
    
    # Start Pyrogram client
    await app.start()
    me = await app.get_me()
    logger.info(f"Userbot STARTED | {me.first_name} (@{me.username})")
    
    # Send startup notification
    await app.send_message(
        "me", 
        f"✅ Userbot online on Railway!\n"
        f"Username: @{me.username}\n"
        f"Time: {time.ctime()}\n"
        f"Send /forward to test"
    )
    
    # Set up graceful shutdown handler
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Shutdown signal received from Railway")
        stop_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows compatibility
            signal.signal(sig, lambda s, f: signal_handler())
    
    # Keep the bot running until stop signal
    logger.info("Bot is running and ready for commands...")
    await stop_event.wait()
    
    # Graceful shutdown
    logger.info("Performing graceful shutdown...")
    await health_server.cleanup()
    await app.stop()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    # Install required dependencies for health check server
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp not found, installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
    
    asyncio.run(main())
