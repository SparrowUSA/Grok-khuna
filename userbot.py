import os
import asyncio
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_name = os.getenv("SESSION_NAME", "userbot_session")

app = Client(
    session_name,
    api_id=api_id,
    api_hash=api_hash,
    # phone_number=os.getenv("PHONE")  # uncomment ONLY for first login, then remove
)

def parse_tg_link(link: str):
    parsed = urlparse(link)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) != 3 or path_parts[0] != 'c':
        raise ValueError("Invalid link. Use format: https://t.me/c/123456789/123")
    channel_str = path_parts[1]
    message_id = int(path_parts[2])
    channel_id = int(f"-100{channel_str}")
    return channel_id, message_id

async def process_message(client: Client, channel_id: int, msg_id: int):
    try:
        msg = await client.get_messages(channel_id, msg_id)
        if not msg:
            await client.send_message("me", f"Message {msg_id} not found or inaccessible.")
            return

        if msg.text:
            await client.send_message("me", msg.text)
        elif msg.video or msg.document:
            # Download → upload (large files handled in chunks)
            file_path = await client.download_media(
                msg,
                file_name=f"/tmp/{msg_id}_{msg.media.file_name or 'video.mp4'}"
            )
            if msg.video:
                await client.send_video("me", file_path, caption=msg.caption, supports_streaming=True)
            else:
                await client.send_document("me", file_path, caption=msg.caption)
            os.remove(file_path)  # cleanup
        else:
            await client.send_message("me", f"Skipped {msg_id} — unsupported type")
    except FloodWait as e:
        print(f"Flood wait {e.value}s")
        await asyncio.sleep(e.value)
    except Exception as e:
        await client.send_message("me", f"Error {msg_id}: {str(e)}")

@app.on_message(filters.command("forward") & filters.me)
async def single_forward(client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /forward https://t.me/c/xxxxxx/123")
        return
    try:
        channel_id, msg_id = parse_tg_link(message.command[1])
        await message.reply(f"Processing single message {msg_id}...")
        await process_message(client, channel_id, msg_id)
        await message.reply("Done!")
    except Exception as e:
        await message.reply(str(e))

@app.on_message(filters.command("batch") & filters.me)
async def batch_forward(client, message: Message):
    if len(message.command) < 3:
        await message.reply("Usage: /batch https://t.me/c/xxxxxx/100 https://t.me/c/xxxxxx/200")
        return
    try:
        start_ch, start_id = parse_tg_link(message.command[1])
        end_ch, end_id = parse_tg_link(message.command[2])
        if start_ch != end_ch:
            await message.reply("Start & end must be same channel!")
            return

        await message.reply(f"Starting batch {start_id} → {end_id} (please wait)...")
        for mid in range(start_id, end_id + 1):
            await process_message(client, start_ch, mid)
            await asyncio.sleep(1.5)  # anti-flood
        await message.reply("Batch finished!")
    except Exception as e:
        await message.reply(str(e))

print("Userbot starting...")
app.run()
