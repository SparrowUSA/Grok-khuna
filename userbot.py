import os
import sys
import subprocess

# ============================================================================
# FORCE INSTALL TgCrypto IF MISSING (Critical for Railway)
# ============================================================================
try:
    import TgCrypto
    print("✓ TgCrypto is installed - Fast encryption enabled")
except ImportError:
    print("⚠️ Installing TgCrypto for better performance...")
    try:
        # Method 1: Install specific version
        subprocess.check_call([sys.executable, "-m", "pip", "install", "TgCrypto==1.2.5"])
        print("✓ TgCrypto 1.2.5 installed successfully")
        
        # Verify installation
        import TgCrypto
        print("✓ TgCrypto verification passed")
    except Exception as e:
        print(f"✗ Failed to install TgCrypto: {e}")
        print("⚠️ Bot will run slower but will still work")

# ============================================================================
# NOW CONTINUE WITH IMPORTS
# ============================================================================
import asyncio
import logging
import signal
import time
from urllib.parse import urlparse
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
# CONFIG FROM ENVIRONMENT (Railway)
# ============================================================================
SESSION_STRING = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", 8080))
HEALTH_CHECK_PATH = os.getenv("HEALTH_CHECK_PATH", "/health")

# Validate required environment variables
if not SESSION_STRING:
    logger.critical("❌ SESSION_STRING is required! Add it in Railway Variables.")
    sys.exit(1)

# ============================================================================
# CLIENT INITIALIZATION
# ============================================================================
app = Client(
    name="restricted_forwarder",
    session_string=SESSION_STRING,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    in_memory=True,
    sleep_threshold=30,
)

# ============================================================================
# HEALTH CHECK SERVER (Required for Railway)
# ============================================================================
async def health_check(request):
    """Health check endpoint for Railway"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Start HTTP server for health checks"""
    server = web.Application()
    server.router.add_get(HEALTH_CHECK_PATH, health_check)
    server.router.add_get("/", health_check)
    
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Health check server running on port {PORT}")
    return runner

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_tg_link(link: str) -> tuple:
    """Parse Telegram link to get channel ID and message ID"""
    try:
        # Remove any whitespace
        link = link.strip()
        
        # Handle t.me/c/123456789/100 format
        if "/c/" in link:
            parts = link.split("/")
            channel_part = parts[parts.index("c") + 1]
            message_id = parts[-1]
            channel_id = int(f"-100{channel_part}")
        else:
            # Handle other formats
            parsed = urlparse(link)
            path = parsed.path.strip('/').split('/')
            
            if len(path) >= 2:
                if path[0] == 'c' and len(path) >= 3:
                    channel_id = int(f"-100{path[1]}")
                    message_id = int(path[2])
                else:
                    # Public channel or username
                    channel_id = path[0]
                    message_id = int(path[1])
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
        
        logger.info(f"Processing message {msg_id}")
        
        # Text message
        if msg.text:
            await client.send_message("me", msg.text)
            return True, f"Text forwarded: {msg_id}"
        
        # Media message
        elif msg.media:
            # Download
            file_path = await client.download_media(msg)
            
            if not file_path:
                return False, f"Failed to download media {msg_id}"
            
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
                    return False, f"Unsupported media type: {msg_id}"
                
                return True, f"Media forwarded: {msg_id}"
                
            finally:
                # Cleanup
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
        else:
            return False, f"No processable content: {msg_id}"
            
    except errors.FloodWait as fw:
        logger.warning(f"Flood wait: {fw.value} seconds")
        await asyncio.sleep(fw.value)
        return await process_message(client, channel_id, msg_id)
    except Exception as e:
        logger.error(f"Error processing {msg_id}: {e}")
        return False, f"Error: {str(e)}"

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
        status_msg = await message.reply(f"🔄 Processing message {msg_id}...")
        
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
        await message.reply("❓ Usage: /batch start_link end_link")
        return
    
    try:
        start_ch, start_id = parse_tg_link(message.command[1])
        end_ch, end_id = parse_tg_link(message.command[2])
        
        if start_ch != end_ch:
            await message.reply("❌ Both links must be from same channel")
            return
        
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        
        total = end_id - start_id + 1
        status_msg = await message.reply(f"📦 Batch: {start_id}→{end_id} ({total} messages)")
        
        success_count = 0
        for idx, mid in enumerate(range(start_id, end_id + 1), 1):
            success, _ = await process_message(client, start_ch, mid)
            if success:
                success_count += 1
            
            # Update progress every 10 messages
            if idx % 10 == 0:
                await status_msg.edit_text(
                    f"📦 Progress: {idx}/{total}\n"
                    f"✅ Success: {success_count}/{idx}"
                )
            
            # Anti-flood delay
            await asyncio.sleep(1.5)
        
        await status_msg.edit_text(
            f"📦 Batch complete!\n"
            f"✅ {success_count}/{total} successful\n"
            f"⚡ {success_count/total*100:.1f}% success rate"
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
        f"🤖 **UserBot Status**\n"
        f"├ User: {client.me.first_name}\n"
        f"├ ID: `{client.me.id}`\n"
        f"├ Uptime: {hours}h {minutes}m\n"
        f"├ Platform: Railway\n"
        f"└ Health: ✅ Online\n\n"
        f"**Commands:**\n"
        f"• `/forward link` - Forward single message\n"
        f"• `/batch start end` - Forward multiple\n"
        f"• `/status` - Show this status"
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
    
    # Start health check server
    health_server = await start_health_server()
    
    # Start Pyrogram client
    await app.start()
    me = await app.get_me()
    logger.info(f"✅ Userbot STARTED | {me.first_name} (@{me.username})")
    
    # Send startup notification
    await app.send_message(
        "me",
        f"🤖 **UserBot Started!**\n"
        f"Time: {time.ctime()}\n"
        f"User: {me.first_name}\n"
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
    
    logger.info("🚀 Bot is running and ready...")
    
    # Keep running
    await stop_event.wait()
    
    # Graceful shutdown
    logger.info("👋 Shutting down...")
    await app.stop()
    await health_server.cleanup()
    logger.info("✅ Shutdown complete")

if __name__ == "__main__":
    # Install aiohttp if missing
    try:
        import aiohttp
    except ImportError:
        print("📦 Installing aiohttp...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp==3.9.5"])
        print("✅ aiohttp installed")
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}")
        sys.exit(1)
