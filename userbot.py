# userbot.py - Optimized for Railway with TgCrypto
import os
import asyncio
import logging
import signal
import time
import sys
from urllib.parse import urlparse
from pyrogram import Client, filters, errors, idle
from pyrogram.types import Message
from aiohttp import web

# Check for TgCrypto and install if missing
try:
    import TgCrypto
    logger = logging.getLogger(__name__)
    logger.info("✓ TgCrypto is installed - Fast encryption enabled")
except ImportError:
    print("⚠️ TgCrypto not found. Installing for better performance...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "TgCrypto"])
    print("✓ TgCrypto installed successfully")

# ─── LOGGING SETUP ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("userbot")
logger.setLevel(logging.INFO)

# ─── CONFIG FROM RAILWAY ENV ──────────────────────────────────────────────
SESSION_STRING = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", 8080))
HEALTH_CHECK_PATH = os.getenv("HEALTH_CHECK_PATH", "/health")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validate required environment variables
if not SESSION_STRING:
    logger.critical("SESSION_STRING is required! Add it in Railway Variables.")
    sys.exit(1)

# Set log level from env
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

# ─── CLIENT INIT ───────────────────────────────────────────────────────────
app = Client(
    name="restricted_forwarder",
    session_string=SESSION_STRING,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True,
    sleep_threshold=30,  # Better for Railway's network
    workers=16,  # Reduced for Railway's limited resources
)

# ─── HEALTH CHECK SERVER ──────────────────────────────────────────────────
async def health_check(request):
    """Enhanced health check with bot status"""
    status = {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "telegram-userbot",
        "uptime": time.time() - start_time,
    }
    
    # Check if bot is connected
    if app.is_connected:
        status["bot_status"] = "connected"
        status["user_id"] = app.me.id if hasattr(app, 'me') else None
    else:
        status["bot_status"] = "disconnected"
        status["status"] = "unhealthy"
    
    return web.json_response(status)

async def start_health_server():
    """Start HTTP server for Railway health checks"""
    server = web.Application()
    server.router.add_get(HEALTH_CHECK_PATH, health_check)
    server.router.add_get("/", health_check)  # Root endpoint too
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Health check server running on http://0.0.0.0:{PORT}{HEALTH_CHECK_PATH}")
    return runner

# ─── UTILITIES ──────────────────────────────────────────────────────────────

def parse_tg_link(link: str) -> tuple[int, int]:
    """Parse Telegram channel link to get channel ID and message ID"""
    try:
        parsed = urlparse(link)
        path = parsed.path.strip('/').split('/')
        
        if len(path) < 2:
            raise ValueError("Invalid link format")
        
        # Handle both formats: c/123456789/100 and +ABC123xyz/100
        if path[0] == 'c' and len(path) == 3:
            channel_id = int(f"-100{path[1]}")
            msg_id = int(path[2])
        elif path[0].startswith('+') or len(path) == 2:
            # For public channels: t.me/channel_name/123
            channel_id = path[0]
            msg_id = int(path[1])
        else:
            raise ValueError("Unsupported link format")
            
        return channel_id, msg_id
    except Exception as e:
        raise ValueError(f"Failed to parse link: {str(e)}")


async def progress_callback(current: int, total: int, message: Message = None):
    """Progress callback with optional message updates"""
    if total == 0:
        return
    
    percentage = (current / total) * 100
    
    # Log every 25%
    if int(percentage) % 25 == 0 and int(percentage) > 0:
        logger.debug(f"Upload progress: {percentage:.1f}%")
    
    # Update message every 10% if message provided
    if message and int(percentage) % 10 == 0:
        try:
            await message.edit_text(f"📤 Uploading: {percentage:.1f}%")
        except:
            pass


async def process_message(client: Client, channel_id: int, msg_id: int, status_msg: Message = None):
    """Process and forward a single message"""
    try:
        # Get the message
        msg = await client.get_messages(channel_id, msg_id)
        if not msg or msg.empty:
            if status_msg:
                await status_msg.edit_text(f"❌ Message {msg_id} not found or deleted")
            return False

        logger.info(f"📨 Processing message {msg_id} | Type: {msg.media.__class__.__name__ if msg.media else 'Text'}")

        # Text message
        if msg.text:
            await client.send_message("me", msg.text)
            return True

        # Media message
        elif msg.media:
            if status_msg:
                await status_msg.edit_text(f"⬇️ Downloading media...")
            
            # Download media
            file_path = await client.download_media(
                msg,
                progress=lambda c, t: progress_callback(c, t, status_msg)
            )

            if not file_path:
                if status_msg:
                    await status_msg.edit_text(f"❌ Failed to download media")
                return False

            try:
                # Upload based on media type
                if status_msg:
                    await status_msg.edit_text(f"⬆️ Uploading media...")
                
                if msg.video:
                    await client.send_video(
                        "me",
                        file_path,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                        supports_streaming=True,
                        progress=lambda c, t: progress_callback(c, t, status_msg)
                    )
                elif msg.document:
                    await client.send_document(
                        "me",
                        file_path,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                        progress=lambda c, t: progress_callback(c, t, status_msg)
                    )
                elif msg.photo:
                    await client.send_photo(
                        "me",
                        file_path,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    )
                elif msg.audio:
                    await client.send_audio(
                        "me",
                        file_path,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities
                    )
                else:
                    logger.warning(f"Unsupported media type in message {msg_id}")
                    if status_msg:
                        await status_msg.edit_text(f"⚠️ Unsupported media type")
                    return False
                
                return True
                
            finally:
                # Cleanup
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up: {file_path}")

        else:
            logger.warning(f"Message {msg_id} has no processable content")
            if status_msg:
                await status_msg.edit_text(f"⚠️ No processable content")
            return False

    except errors.FloodWait as fw:
        wait_time = fw.value
        logger.warning(f"⏳ FloodWait: {wait_time} seconds")
        if status_msg:
            await status_msg.edit_text(f"⏳ Flood wait: {wait_time}s")
        await asyncio.sleep(wait_time)
        return await process_message(client, channel_id, msg_id, status_msg)
    
    except errors.RPCError as e:
        logger.error(f"Telegram error on {msg_id}: {e}")
        if status_msg:
            await status_msg.edit_text(f"❌ Telegram error: {e}")
        return False
    
    except Exception as e:
        logger.error(f"Unexpected error on {msg_id}: {type(e).__name__}: {e}")
        if status_msg:
            await status_msg.edit_text(f"💥 Error: {str(e)[:100]}")
        return False


# ─── COMMAND HANDLERS ───────────────────────────────────────────────────────

@app.on_message(filters.command("forward", prefixes="/") & filters.me)
async def single_forward(client: Client, message: Message):
    """Forward a single message from a restricted channel"""
    if len(message.command) < 2:
        await message.reply("❓ Usage: `/forward https://t.me/c/xxxx/123`")
        return

    try:
        channel_id, msg_id = parse_tg_link(message.command[1])
        status_msg = await message.reply(f"🔄 Processing message {msg_id}...")
        
        success = await process_message(client, channel_id, msg_id, status_msg)
        
        if success:
            await status_msg.edit_text(f"✅ Message {msg_id} forwarded successfully!")
        else:
            await status_msg.edit_text(f"❌ Failed to forward message {msg_id}")
            
    except ValueError as e:
        await message.reply(f"❌ Invalid link format:\n`{str(e)}`")
    except Exception as e:
        logger.exception(f"Error in /forward command")
        await message.reply(f"💥 Unexpected error:\n`{type(e).__name__}: {str(e)[:200]}`")


@app.on_message(filters.command("batch", prefixes="/") & filters.me)
async def batch_forward(client: Client, message: Message):
    """Forward a range of messages"""
    if len(message.command) < 3:
        await message.reply("❓ Usage: `/batch start_link end_link`")
        return

    try:
        start_ch, start_id = parse_tg_link(message.command[1])
        end_ch, end_id = parse_tg_link(message.command[2])
        
        if start_ch != end_ch:
            await message.reply("❌ Both links must be from the same channel")
            return

        if start_id > end_id:
            start_id, end_id = end_id, start_id  # Swap if reversed

        total = end_id - start_id + 1
        status_msg = await message.reply(f"📦 Batch started: {start_id} → {end_id}\nTotal: {total} messages")
        
        success_count = 0
        fail_count = 0
        
        for idx, mid in enumerate(range(start_id, end_id + 1), 1):
            # Update progress every 10 messages or 10%
            if idx % 10 == 0 or idx % max(1, total // 10) == 0:
                progress = (idx / total) * 100
                await status_msg.edit_text(
                    f"📦 Processing batch...\n"
                    f"Progress: {idx}/{total} ({progress:.1f}%)\n"
                    f"✅ Success: {success_count} | ❌ Failed: {fail_count}"
                )
            
            success = await process_message(client, start_ch, mid)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # Anti-flood delay
            await asyncio.sleep(1.5)
        
        await status_msg.edit_text(
            f"📦 Batch complete!\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"⚡ Success rate: {(success_count/total*100):.1f}%"
        )
        
    except Exception as e:
        logger.exception(f"Error in /batch command")
        await message.reply(f"💥 Batch failed:\n`{type(e).__name__}: {str(e)[:200]}`")


@app.on_message(filters.command("status", prefixes="/") & filters.me)
async def status_command(client: Client, message: Message):
    """Check bot status and uptime"""
    uptime = time.time() - start_time
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    status_text = (
        f"🤖 **UserBot Status**\n"
        f"├ User: {client.me.first_name} (@{client.me.username})\n"
        f"├ ID: `{client.me.id}`\n"
        f"├ Uptime: {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
        f"├ Connected: {'✅' if client.is_connected else '❌'}\n"
        f"├ Platform: Railway\n"
        f"└ Version: Pyrogram {pyrogram.__version__}\n\n"
        f"**Commands:**\n"
        f"• `/forward link` - Forward single message\n"
        f"• `/batch start end` - Forward range of messages\n"
        f"• `/status` - Show this status"
    )
    
    await message.reply(status_text, disable_web_page_preview=True)


# ─── STARTUP AND SHUTDOWN ──────────────────────────────────────────────────
start_time = time.time()

async def main():
    """Main entry point with proper startup and shutdown handling"""
    global start_time
    start_time = time.time()
    
    # Start health check server
    health_server = None
    try:
        health_server = await start_health_server()
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")
        # Continue without health server
    
    # Start Pyrogram client
    try:
        await app.start()
        me = await app.get_me()
        logger.info(f"✅ Userbot STARTED | {me.first_name} (@{me.username}) | ID: {me.id}")
        
        # Send startup notification
        try:
            await app.send_message(
                "me",
                f"🤖 **UserBot Started Successfully!**\n"
                f"├ Time: {time.ctime()}\n"
                f"├ Platform: Railway\n"
                f"├ User: {me.first_name}\n"
                f"└ ID: `{me.id}`\n\n"
                f"**Ready to process commands!**\n"
                f"Use `/status` to check bot status."
            )
        except Exception as e:
            logger.warning(f"Failed to send startup message: {e}")
        
        # Set up graceful shutdown
        stop_event = asyncio.Event()
        
        def signal_handler():
            logger.info("🛑 Shutdown signal received")
            stop_event.set()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
            except (NotImplementedError, RuntimeError):
                # Fallback for Windows or if loop not running
                signal.signal(sig, lambda s, f: signal_handler())
        
        logger.info("🚀 Bot is running and ready for commands...")
        
        # Keep running until shutdown signal
        await stop_event.wait()
        
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        raise
    
    finally:
        # Graceful shutdown
        logger.info("🛑 Performing graceful shutdown...")
        
        try:
            await app.stop()
            logger.info("✅ Pyrogram client stopped")
        except Exception as e:
            logger.error(f"Error stopping client: {e}")
        
        if health_server:
            try:
                await health_server.cleanup()
                logger.info("✅ Health server stopped")
            except Exception as e:
                logger.error(f"Error stopping health server: {e}")
        
        logger.info("👋 Shutdown complete")


if __name__ == "__main__":
    # Install missing dependencies
    required_packages = ["aiohttp"]
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            logger.info(f"📦 Installing {package}...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            logger.info(f"✅ {package} installed")
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
