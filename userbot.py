# userbot.py
import os
import asyncio
import time
from urllib.parse import urlparse
from pyrogram import Client, filters, errors
from pyrogram.types import Message
from pyrogram.raw.types import InputMediaUploadedDocument

# ─── CONFIG ────────────────────────────────────────────────────────────────
SESSION_STRING = os.getenv("SESSION_STRING")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not SESSION_STRING:
    raise ValueError("SESSION_STRING environment variable is required!")

# Optional - useful for debugging
if API_ID and API_HASH:
    print("API_ID and API_HASH are present - will be used")
else:
    print("Running in session string only mode (recommended)")

# ─── CLIENT ────────────────────────────────────────────────────────────────
app = Client(
    name="restricted_forwarder",
    session_string=SESSION_STRING,
    api_id=int(API_ID) if API_ID else None,
    api_hash=API_HASH if API_HASH else None,
    # in_memory=True  # ← uncomment if you want no session file at all
)

# ─── UTILITIES ─────────────────────────────────────────────────────────────

def parse_message_link(link: str) -> tuple[int, int]:
    """Parse https://t.me/c/111111111/123 → (channel_id, message_id)"""
    parsed = urlparse(link)
    path = parsed.path.strip('/').split('/')
    
    if len(path) != 3 or path[0] != 'c':
        raise ValueError("Invalid Telegram link format.\nUse: https://t.me/c/xxxxxxxxxx/123")
    
    channel_str = path[1]
    msg_id = int(path[2])
    
    # Private/supergroup channels have -100 prefix
    channel_id = int(f"-100{channel_str}")
    
    return channel_id, msg_id


async def progress(current: int, total: int):
    """Simple progress callback for download/upload"""
    percent = current * 100 / total
    if percent % 10 < 1:  # report every ~10%
        print(f"Progress: {percent:.1f}%")


async def process_and_forward(client: Client, channel_id: int, msg_id: int):
    """Core function: get → download if media → forward as new message"""
    try:
        msg = await client.get_messages(channel_id, msg_id)
        if not msg:
            await client.send_message("me", f"Message {msg_id} not found or inaccessible")
            return

        # Text message
        if msg.text or msg.caption:
            await client.send_message(
                "me",
                msg.text or msg.caption,
                reply_to_message_id=msg_id if msg.text else None
            )

        # Video / Document / Photo / etc.
        elif msg.media:
            file_path = await client.download_media(
                msg,
                progress=progress,
                block=False
            )

            if msg.video:
                await client.send_video(
                    "me",
                    file_path,
                    caption=msg.caption,
                    supports_streaming=True,
                    progress=progress,
                    block=False
                )
            elif msg.document:
                await client.send_document(
                    "me",
                    file_path,
                    caption=msg.caption,
                    progress=progress,
                    block=False
                )
            elif msg.photo:
                await client.send_photo(
                    "me",
                    file_path,
                    caption=msg.caption
                )
            else:
                await client.send_message("me", f"Skipped {msg_id} - unsupported media type")

            # Cleanup
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

        else:
            await client.send_message("me", f"Skipped {msg_id} - no content")

    except errors.FloodWait as e:
        print(f"FloodWait: sleeping {e.value} seconds...")
        await asyncio.sleep(e.value)
    except Exception as e:
        error_msg = f"Error processing {msg_id}: {type(e).__name__} - {str(e)}"
        print(error_msg)
        await client.send_message("me", error_msg)


# ─── COMMANDS ──────────────────────────────────────────────────────────────

@app.on_message(filters.command("forward") & filters.me)
async def cmd_single_forward(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage:\n/forward https://t.me/c/xxxxxx/123")

    try:
        link = message.command[1]
        channel_id, msg_id = parse_message_link(link)
        
        await message.reply(f"Starting single forward → {msg_id}")
        await process_and_forward(client, channel_id, msg_id)
        await message.reply("✓ Done")
        
    except ValueError as e:
        await message.reply(str(e))
    except Exception as e:
        await message.reply(f"Error: {str(e)}")


@app.on_message(filters.command("batch") & filters.me)
async def cmd_batch_forward(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply("Usage:\n/batch https://t.me/c/xxxx/100 https://t.me/c/xxxx/150")

    try:
        start_link = message.command[1]
        end_link = message.command[2]

        start_ch, start_id = parse_message_link(start_link)
        end_ch, end_id = parse_message_link(end_link)

        if start_ch != end_ch:
            return await message.reply("Both links must be from the same channel")

        await message.reply(f"Batch processing {start_id} → {end_id} (may take time)")

        processed = 0
        for msg_id in range(start_id, end_id + 1):
            await process_and_forward(client, start_ch, msg_id)
            processed += 1
            # Basic flood protection
            if processed % 5 == 0:
                await asyncio.sleep(1.5)
            else:
                await asyncio.sleep(0.8)

        await message.reply(f"Batch finished • {processed} messages processed")

    except ValueError as e:
        await message.reply(str(e))
    except Exception as e:
        await message.reply(f"Batch error: {str(e)}")


# ─── START ─────────────────────────────────────────────────────────────────

async def main():
    await app.start()
    me = await app.get_me()
    print(f"Userbot started successfully!")
    print(f"Logged in as: {me.first_name} (@{me.username})")
    print("Send commands to Saved Messages")
    
    # Keep alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
