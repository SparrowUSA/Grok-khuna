import os
import sys
import asyncio
import logging
import signal
import time
from urllib.parse import urlparse

# Try to import and install missing packages
try:
    import pyrogram
    print(f"✓ Pyrogram {pyrogram.__version__}")
except ImportError:
    print("❌ Pyrogram not found - installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram==2.0.106"])
    import pyrogram

try:
    import tgcrypto
    print("✓ TgCrypto installed")
except ImportError:
    print("❌ TgCrypto not found - installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tgcrypto==1.2.5"])
    import tgcrypto

try:
    import aiohttp
    print(f"✓ aiohttp {aiohttp.__version__}")
except ImportError:
    print("❌ aiohttp not found - installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp==3.9.5"])
    import aiohttp

# Now import from installed packages
from pyrogram import Client, filters, errors
from pyrogram.types import Message
from aiohttp import web

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("userbot")

# ============================================================================
# CONFIG FROM ENVIRONMENT
# ============================================================================
SESSION_STRING = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", 8080))

if not SESSION_STRING:
    logger.critical("❌ SESSION_STRING is required! Add it in Railway Variables.")
    sys.exit(1)

# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================
app = Client(
    name="railway_forwarder",
    session_string=SESSION_STRING,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True,
    sleep_threshold=30,
)

# ============================================================================
# HEALTH CHECK SERVER
# ============================================================================
async def health_check(request):
    """Health check endpoint for Railway"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Start HTTP server for Railway health checks"""
    server = web.Application()
    server.router.add_get("/health", health_check)
    server.router.add_get("/", health_check)
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Health server running on port {PORT}")
    return runner

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_tg_link(link: str) -> tuple:
    """Parse Telegram link to get channel ID and message ID"""
    try:
        link = link.strip()
        
        # Handle t.me/c/123456789/100 format
        if "/c/" in link:
            parts = link.split("/")
            # Find index of 'c' and get next part
            c_index = parts.index("c") if "c" in parts else -1
            if c_index != -1 and c_index + 1 < len(parts):
                channel_part = parts[c_index + 1]
                message_id = parts[-1] if parts[-1].isdigit() else "1"
                channel_id = int(f"-100{channel_part}")
                return channel_id, int(message_id)
        
        # Try URL parsing
        parsed = urlparse(link)
        path = parsed.path.strip('/').split('/')
        
        if len(path) >= 2:
            if path[0] == 'c' and len(path) >= 3:
                channel_id = int(f"-100{path[1]}")
                message_id = int(path[2])
            else:
                # For public channels
                channel_id = path[0]
                message_id = int(path[1]) if len(path) > 1 else 1
        else:
            raise ValueError("Invalid link format")
        
        return channel_id, int(message_id)
    except Exception as e:
        raise ValueError(f"Failed to parse link: {str(e)}")

async def process_message(client: Client, channel_id: int, msg_id: int):
    """Process and forward a single message"""
    try:
        # Get the message
        msg = await client.get_messages(channel_id, msg_id)
        if not msg or msg.empty:
            return False, f"Message {msg_id} not found"
        
        logger.info(f"📨 Processing message {msg_id}")
        
        # Text message
        if msg.text:
            await client.send_message("me", msg.text)
            return True, f"Text forwarded: {msg_id}"
        
        # Media message
        elif msg.media:
            # Download
            file_path = await client.download_media(msg)
            
            if not file_path:
                return False, f"Failed to download {msg_id}"
            
            try:
                # Upload based on type
                if msg.video:
                    await client.send_video("me", file_path, caption=msg.caption)
                elif msg.document:
                    await client.send_document("me", file_path, caption=msg.caption)
                elif msg.photo:
                    await client.send_photo("me", file_path, caption=msg.caption)
                elif msg.audio:
                    await client.send_audio("me", file_path, caption=msg.caption)
                else:
                    return False, f"Unsupported media: {msg_id}"
                
                return True, f"Media forwarded: {msg_id}"
                
            finally:
                # Cleanup
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
        else:
            return False, f"No content: {msg_id}"
            
    except errors.FloodWait as fw:
        logger.warning(f"⏳ Flood wait: {fw.value}s")
        await asyncio.sleep(fw.value)
        return await process_message(client, channel_id, msg_id)
    except Exception as e:
        logger.error(f"❌ Error {msg_id}: {e}")
        return False, f"Error: {str(e)[:100]}"

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@app.on_message(filters.command("forward", prefixes="/") & filters.me)
async def single_forward(client: Client, message: Message):
    """Forward a single message"""
    if len(message.command) < 2:
        await message.reply("❓ Usage: /forward https://t.me/c/xxxx/123")
        return
    
    try:
        channel_id, msg_id = parse_tg_link(message.command[1])
        status_msg = await message.reply(f"🔄 Processing {msg_id}...")
        
        success, result = await process_message(client, channel_id, msg_id)
        
        if success:
            await status_msg.edit_text(f"✅ {result}")
        else:
            await status_msg.edit_text(f"❌ {result}")
            
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("batch", prefixes="/") & filters.me)
async def batch_forward(client: Client, message: Message):
    """Forward a range of messages"""
    if len(message.command) < 3:
        await message.reply("❓ Usage: /batch https://t.me/c/xxxx/1 https://t.me/c/xxxx/10")
        return
    
    try:
        start_ch, start_id = parse_tg_link(message.command[1])
        end_ch, end_id = parse_tg_link(message.command[2])
        
        if start_ch != end_ch:
            await message.reply("❌ Links must be from same channel")
            return
        
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        
        total = end_id - start_id + 1
        status_msg = await message.reply(f"📦 Batch: {start_id}→{end_id} ({total} msgs)")
        
        success_count = 0
        for idx, mid in enumerate(range(start_id, end_id + 1), 1):
            success, _ = await process_message(client, start_ch, mid)
            if success:
                success_count += 1
            
            # Update progress
            if idx % 10 == 0 or idx == total:
                progress = (idx / total) * 100
                await status_msg.edit_text(
                    f"📦 Progress: {idx}/{total} ({progress:.1f}%)\n"
                    f"✅ Success: {success_count}"
                )
            
            await asyncio.sleep(1.5)  # Anti-flood
        
        await status_msg.edit_text(
            f"📦 Batch complete!\n"
            f"✅ {success_count}/{total} successful"
        )
        
    except Exception as e:
        await message.reply(f"❌ Batch failed: {str(e)}")

@app.on_message(filters.command("status", prefixes="/") & filters.me)
async def status_command(client: Client, message: Message):
    """Check bot status"""
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    status_text = (
        f"🤖 **Railway UserBot**\n"
        f"├ User: {client.me.first_name}\n"
        f"├ ID: `{client.me.id}`\n"
        f"├ Uptime: {hours}h {minutes}m\n"
        f"└ Status: ✅ Online\n\n"
        f"**Commands:**\n"
        f"• `/forward link` - Forward message\n"
        f"• `/batch start end` - Forward range\n"
        f"• `/status` - Check status"
    )
    
    await message.reply(status_text)

# ============================================================================
# MAIN FUNCTION
# ============================================================================
start_time = time.time()

async def main():
    """Main entry point"""
    global start_time
    start_time = time.time()
    
    # Start health server
    health_server = await start_health_server()
    
    # Start Telegram client
    await app.start()
    me = await app.get_me()
    logger.info(f"✅ Userbot STARTED: {me.first_name} (@{me.username})")
    
    # Startup notification
    await app.send_message(
        "me",
        f"🤖 **Railway UserBot Started**\n"
        f"Time: {time.ctime()}\n"
        f"User: {me.first_name}\n"
        f"ID: `{me.id}`\n\n"
        f"Ready to process commands!"
    )
    
    # Setup graceful shutdown
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("🛑 Shutdown signal received")
        stop_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
        except:
            signal.signal(sig, lambda s, f: signal_handler())
    
    logger.info("🚀 Bot is running and ready for commands...")
    
    # Keep running
    await stop_event.wait()
    
    # Graceful shutdown
    logger.info("👋 Shutting down gracefully...")
    await app.stop()
    await health_server.cleanup()
    logger.info("✅ Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}")
        sys.exit(1)
