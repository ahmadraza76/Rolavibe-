# main.py
import logging
import asyncio
import json
import os
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import StreamType
from pytgcalls.types.input_stream import AudioPiped
import yt_dlp as youtube_dl
from yt_dlp.utils import DownloadError
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import aiofiles
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# ✅ Keep Alive Server
from keep_alive import keep_alive
keep_alive()

# ✅ Logging Setup
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("rolavibe.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ✅ Bot Client
app = Client("RolaVibeBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
call_py = PyTgCalls(app)

# ✅ Global Variables
queue = {}
queue_lock = asyncio.Lock()
is_call_active = False
maintenance_mode = False
MAINTENANCE_FILE = "maintenance_mode.json"
FM_CHANNELS = {
    "Radio Mirchi": "http://example.com/radiomirchi",
    "Red FM": "http://example.com/redfm",
    "Big FM": "http://example.com/bigfm"
}

# ✅ YouTube-DL Options
ydl_opts = {
    'format': 'bestaudio',
    'quiet': True,
    'noplaylist': True
}

# ✅ Spotify API Initialization
sp = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
    except Exception as e:
        logger.error(f"Spotify API Initialization Error: {e}")

# ✅ Helper Functions
async def load_maintenance_mode():
    global maintenance_mode
    try:
        async with aiofiles.open(MAINTENANCE_FILE, "r") as f:
            data = await f.read()
            maintenance_mode = json.loads(data) if data else False
    except (FileNotFoundError, json.JSONDecodeError):
        maintenance_mode = False

async def save_maintenance_mode():
    try:
        async with aiofiles.open(MAINTENANCE_FILE, "w") as f:
            await f.write(json.dumps(maintenance_mode))
    except Exception as e:
        logger.error(f"❌ Maintenance Mode Save Error: {e}")

async def ensure_files_exist():
    files = ["queue.json", "admin_commands.json", "allowed_groups.json"]
    for file in files:
        if not os.path.exists(file):
            async with aiofiles.open(file, "w") as f:
                await f.write(json.dumps({}))

async def load_queue():
    global queue
    try:
        async with aiofiles.open("queue.json", "r") as f:
            data = await f.read()
            queue = json.loads(data) if data else {}
    except (FileNotFoundError, json.JSONDecodeError):
        queue = {}

async def save_queue():
    try:
        async with aiofiles.open("queue.json", "w") as f:
            await f.write(json.dumps(queue))
    except Exception as e:
        logger.error(f"❌ Queue Save Error: {e}")

async def auto_save():
    while True:
        await asyncio.sleep(120)
        try:
            await save_queue()
            await save_maintenance_mode()
        except Exception as e:
            logger.error(f"❌ Auto-Save Error: {e}")

async def is_admin_and_allowed(chat_id, user_id, command):
    try:
        member = await app.get_chat_member(chat_id, user_id)
        if member.status not in ["administrator", "creator"]:
            return False
        async with aiofiles.open("admin_commands.json", "r") as f:
            data = json.loads(await f.read())
            return command in data.get("allowed_admin_commands", [])
    except Exception as e:
        logger.error(f"Admin Check Error: {e}")
        return False

async def get_youtube_video(query):
    loop = asyncio.get_event_loop()
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            return await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False))
    except Exception as e:
        logger.error(f"❌ YouTube Search Error: {e}")
        return None

def get_spotify_song_details(query):
    try:
        if not sp:
            return None
        results = sp.search(q=query, limit=1)
        if results["tracks"]["items"]:
            track = results["tracks"]["items"][0]
            return {
                "title": track["name"],
                "artist": track["artists"][0]["name"],
                "url": track["external_urls"]["spotify"]
            }
        return None
    except Exception as e:
        logger.error(f"❌ Spotify API Error: {e}")
        return None

def get_thumbnail(video_id):
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

async def is_group_allowed(chat_id):
    try:
        async with aiofiles.open("allowed_groups.json", "r") as f:
            data = await f.read()
            allowed_groups = json.loads(data) if data else {}
            return str(chat_id) in allowed_groups
    except (FileNotFoundError, json.JSONDecodeError):
        return False

# ✅ Commands
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    if message.chat.type == "supergroup" and not await is_group_allowed(message.chat.id):
        return await message.reply_text("⚠️ This group is not authorized to use the bot. Please contact the bot owner.")

    if maintenance_mode and message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Bot is currently under maintenance. Please try again later.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎶 Play Music", callback_data="play_music"),
         InlineKeyboardButton("🔊 Volume", callback_data="volume_control")],
        [InlineKeyboardButton("📌 My Playlist", callback_data="my_playlist"),
         InlineKeyboardButton("🎵 Now Playing", callback_data="now_playing")],
        [InlineKeyboardButton("⚙ Settings", callback_data="settings"),
         InlineKeyboardButton("📢 Updates", url="https://t.me/RolaVibeUpdates")],
        [InlineKeyboardButton("📻 Radio", callback_data="radio")]
    ])

    if message.from_user.id == OWNER_ID:
        keyboard.inline_keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])

    await message.reply_text(
        "**✨ Welcome to _Rola Vibe_! 🎶**\n\n"
        "🎧 *Enjoy high-quality music streaming in your groups.*\n"
        "🎶 *Play your favorite songs with just a command!*\n\n"
        "📌 *Join* [@RolaVibeUpdates](https://t.me/RolaVibeUpdates) *for latest updates!*\n\n"
        "👨‍💻 *Developed by* [Mr Nick](https://t.me/5620922625)",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# ✅ Help Command (Admin and Owner Commands Info)
@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    help_text = (
        "✨ **Rola Vibe Bot Help Menu** ✨\n\n"
        "🎵 **For Everyone:**\n"
        "▫️ .start - Bot ko start karein aur welcome message dekhein.\n"
        "▫️ .help - Ye help menu dekhein.\n\n"
        "🔧 **Admin Commands:**\n"
        "▫️ .play <song_name> - Song play karein (Admin only).\n"
        "▫️ .stop - Playback stop karein (Admin only).\n"
        "▫️ .pause - Playback pause karein (Admin only).\n"
        "▫️ .resume - Playback resume karein (Admin only).\n"
        "▫️ .skip - Agla song play karein (Admin only).\n\n"
        "👑 **Owner Commands:**\n"
        "▫️ .enableadmin <command> - Admin command enable karein.\n"
        "▫️ .disableadmin <command> - Admin command disable karein.\n"
        "▫️ .playvideo <video_url> - Video play karein (Owner only).\n"
        "▫️ .addgroup - Group ko bot mein add karein (Owner only).\n\n"
        "📌 *Note:* Admin commands sirf group admins aur bot owner use kar sakte hain.\n"
        "🎧 *Enjoy the Rola Vibe!* 🎶"
    )

    await message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 ROLA CHAT", url="https://t.me/RolaVibeChat"),
             InlineKeyboardButton("👨‍💻 DEVELOPER", url="https://t.me/5620922625")]
        ])
    )

# 🎵 Play/Rola Command (Admin Check)
@app.on_message(filters.command(["play", "rola"], prefixes=".") & filters.group)
async def play_rola_command(client, message: Message):
    if not await is_group_allowed(message.chat.id):
        return await message.reply_text("⚠️ This group is not authorized to use the bot. Please contact the bot owner.")

    global is_call_active
    chat_id = message.chat.id
    user = message.from_user

    if maintenance_mode and user.id != OWNER_ID:
        return await message.reply_text("⚠️ Bot is currently under maintenance. Please try again later.")

    if not await is_admin_and_allowed(chat_id, user.id, "play"):
        return await message.reply_text("⚠️ *Only admins can use this command!*")

    query = " ".join(message.command[1:]) if len(message.command) > 1 else None
    if not query:
        return await message.reply_text("⚠️ *Please provide a song name!*")

    await message.delete()
    searching_msg = await message.reply_text("🔍 *Searching...*")

    try:
        # Fetch song details from Spotify
        spotify_song = get_spotify_song_details(query)
        if not spotify_song:
            return await searching_msg.edit("⚠️ *No results found on Spotify. Please try another name.*")

        # Search YouTube for the song
        info = await get_youtube_video(f"{spotify_song['title']} {spotify_song['artist']}")
        if "entries" in info and len(info["entries"]) > 0:
            video = info["entries"][0]
        else:
            raise DownloadError("No results found.")
            
        video_url = video["url"]
        title = video["title"]
        video_id = video["id"]
        duration = video["duration"]

        # Check song duration
        if duration > 600:  # 10 minutes
            return await searching_msg.edit("⚠️ *Song is too long. Maximum allowed duration is 10 minutes.*")
    except DownloadError:
        return await searching_msg.edit("⚠️ *No results found. Please try another name.*")
    except Exception as e:
        logger.error(f"Play Command Error: {e}")
        return await searching_msg.edit("⚠️ *An error occurred. Please try again later.*")

    await searching_msg.delete()

    # Add song to queue
    async with queue_lock:
        queue.setdefault(chat_id, []).append((video_url, title, video_id))
        await save_queue()

    # Join voice call if not already joined
    if not is_call_active:
        await call_py.join_group_call(
            chat_id,
            AudioPiped(video_url, stream_type=StreamType().pulse_stream)
        )
        is_call_active = True

    # Send now playing message with Expand option
    await message.reply_photo(
        photo=get_thumbnail(video_id),
        caption=f"🎵 **Now Playing:** `{title}`\n"
                f"🔗 [Watch on YouTube](https://youtu.be/{video_id})\n\n"
                "🎧 *Enjoy the Rola Vibe!*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause"),
             InlineKeyboardButton("▶️ Resume", callback_data="resume"),
             InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
             InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
            [InlineKeyboardButton("🔍 Expand", callback_data="expand")]
        ])
    )

# ✅ Expand Callback
@app.on_callback_query(filters.regex("^expand$"))
async def expand_callback(client, callback_query):
    chat_id = callback_query.message.chat.id
    if "content" in queue.get(chat_id, {}):
        content = queue[chat_id]["content"]
        await callback_query.edit_message_text(
            f"🔍 **Expanded Content:**\n\n{content}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏏️ Collapse", callback_data="collapse")]
            ])
        )
    else:
        await callback_query.answer("⚠️ No content available to expand.", show_alert=True)

# ✅ Collapse Callback
@app.on_callback_query(filters.regex("^collapse$"))
async def collapse_callback(client, callback_query):
    await callback_query.edit_message_text("Content collapsed.")

# 🎵 Stop Command (Admin Check)
@app.on_message(filters.command("stop", prefixes=".") & filters.group)
async def stop(client, message: Message):
    global is_call_active
    chat_id = message.chat.id
    user = message.from_user

    if not await is_admin_and_allowed(chat_id, user.id, "stop"):
        return await message.reply_text("⚠️ *Only admins can use this command!*")

    async with queue_lock:
        queue.pop(chat_id, None)
        await save_queue()

    if is_call_active:
        await call_py.leave_group_call(chat_id)
        is_call_active = False
    await message.reply_text("🛑 *Playback stopped.*")

# ✅ Owner Commands: Enable/Disable Admin Commands
@app.on_message(filters.command("enableadmin", prefixes=".") & filters.user(OWNER_ID))
async def enable_admin_command(client, message: Message):
    cmd = message.text.split(" ", 1)[1].strip()
    async with aiofiles.open("admin_commands.json", "r+") as f:
        data = json.loads(await f.read())
        if cmd not in data["allowed_admin_commands"]:
            data["allowed_admin_commands"].append(cmd)
            await f.seek(0)
            await f.write(json.dumps(data))
            return await message.reply_text(f"✅ *Admin command `{cmd}` enabled!*")

@app.on_message(filters.command("disableadmin", prefixes=".") & filters.user(OWNER_ID))
async def disable_admin_command(client, message: Message):
    cmd = message.text.split(" ", 1)[1].strip()
    async with aiofiles.open("admin_commands.json", "r+") as f:
        data = json.loads(await f.read())
        if cmd in data["allowed_admin_commands"]:
            data["allowed_admin_commands"].remove(cmd)
            await f.seek(0)
            await f.write(json.dumps(data))
            return await message.reply_text(f"✅ *Admin command `{cmd}` disabled!*")

# 🎥 Play Video Command (Owner Only)
@app.on_message(filters.command("playvideo", prefixes=".") & filters.user(OWNER_ID))
async def play_video_command(client, message: Message):
    global is_call_active
    chat_id = message.chat.id
    user = message.from_user

    # Check if user is the bot owner
    if user.id != OWNER_ID:
        return await message.reply_text("⚠️ *Only the bot owner can use this command!*")

    # Get video URL from command
    video_url = " ".join(message.command[1:]) if len(message.command) > 1 else None
    if not video_url:
        return await message.reply_text("⚠️ *Please provide a video URL!*")

    await message.delete()
    searching_msg = await message.reply_text("🔍 *Processing video...*")

    try:
        # Use yt-dlp to extract video info
        loop = asyncio.get_event_loop()
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(video_url, download=False))
            if not info:
                return await searching_msg.edit("⚠️ *No video found at the provided URL.*")

            video_title = info.get("title", "Unknown Title")
            video_url = info.get("url")  # Direct video stream URL
            video_duration = info.get("duration", 0)

            # Check video duration (max 3 hours = 180 minutes = 10800 seconds)
            if video_duration > 10800:
                return await searching_msg.edit("⚠️ *Video is too long. Maximum allowed duration is 3 hours.*")

    except DownloadError:
        return await searching_msg.edit("⚠️ *Invalid URL or unsupported website.*")
    except Exception as e:
        logger.error(f"Video Play Error: {e}")
        return await searching_msg.edit("⚠️ *An error occurred. Please try again later.*")

    await searching_msg.delete()

    # Add video to queue
    async with queue_lock:
        queue.setdefault(chat_id, []).append((video_url, video_title, "video"))
        await save_queue()

    # Join voice call if not already joined
    if not is_call_active:
        await call_py.join_group_call(
            chat_id,
            AudioPiped(video_url, stream_type=StreamType().pulse_stream)
        )
        is_call_active = True

    # Send now playing message
    await message.reply_text(
        f"🎥 **Now Playing Video:** `{video_title}`\n"
        f"🔗 [Watch Video]({video_url})\n\n"
        "🎧 *Enjoy the Rola Vibe!*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause"),
             InlineKeyboardButton("▶️ Resume", callback_data="resume"),
             InlineKeyboardButton("⏭️ Skip", callback_data="skip"),
             InlineKeyboardButton("⏹️ Stop", callback_data="stop")],
            [InlineKeyboardButton("🔍 Expand", callback_data="expand")]
        ])
    )

# ✅ Owner Panel Callback
@app.on_callback_query(filters.regex("^owner_panel$"))
async def owner_panel_callback(client, callback_query):
    user = callback_query.from_user

    # ✅ Check if user is the bot owner
    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    # ✅ Owner Panel Options
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="bot_stats"),
         InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("🔧 Maintenance", callback_data="maintenance"),
         InlineKeyboardButton("🔒 Admin Commands", callback_data="admin_commands")],
        [InlineKeyboardButton("📝 Check Logs", callback_data="check_logs"),
         InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ])

    await callback_query.edit_message_text(
        "👑 **Owner Panel**\n\n"
        "Welcome to the bot owner's control panel. Choose an option below:",
        reply_markup=keyboard
    )

# ✅ Bot Stats Callback
@app.on_callback_query(filters.regex("^bot_stats$"))
async def bot_stats_callback(client, callback_query):
    user = callback_query.from_user

    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    # ✅ Fetch Bot Stats (Example)
    total_users = 1000  # Replace with actual logic to fetch stats
    total_groups = 50   # Replace with actual logic to fetch stats

    await callback_query.edit_message_text(
        f"📊 **Bot Statistics**\n\n"
        f"👤 Total Users: `{total_users}`\n"
        f"👥 Total Groups: `{total_groups}`\n\n"
        "🔙 Click the button below to go back.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
        ])
    )

# ✅ Broadcast Message Callback
@app.on_callback_query(filters.regex("^broadcast$"))
async def broadcast_callback(client, callback_query):
    user = callback_query.from_user

    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    await callback_query.edit_message_text(
        "📢 **Broadcast Message**\n\n"
        "Send the message you want to broadcast to all users/groups.\n\n"
        "🔙 Click the button below to go back.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
        ])
    )

# ✅ Maintenance Mode Callback
@app.on_callback_query(filters.regex("^maintenance$"))
async def maintenance_callback(client, callback_query):
    global maintenance_mode
    user = callback_query.from_user

    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    # ✅ Toggle Maintenance Mode
    maintenance_mode = not maintenance_mode

    await callback_query.edit_message_text(
        f"🔧 **Maintenance Mode**\n\n"
        f"Maintenance mode is currently `{'ON' if maintenance_mode else 'OFF'}`.\n\n"
        "🔙 Click the button below to go back.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
        ])
    )

# ✅ Admin Commands Management Callback
@app.on_callback_query(filters.regex("^admin_commands$"))
async def admin_commands_callback(client, callback_query):
    user = callback_query.from_user

    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    # ✅ Fetch Admin Commands (Example)
    admin_commands = [".play", ".stop", ".pause", ".resume", ".skip"]

    await callback_query.edit_message_text(
        f"🔒 **Admin Commands Management**\n\n"
        f"Current allowed admin commands:\n"
        f"{', '.join(admin_commands)}\n\n"
        "🔙 Click the button below to go back.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
        ])
    )

# ✅ Check Logs Callback
@app.on_callback_query(filters.regex("^check_logs$"))
async def check_logs_callback(client, callback_query):
    user = callback_query.from_user

    if user.id != OWNER_ID:
        await callback_query.answer("⚠️ Only the bot owner can access this panel!", show_alert=True)
        return

    # ✅ Send Logs File (Example)
    try:
        await client.send_document(
            chat_id=user.id,
            document="rolavibe.log",
            caption="📝 **Bot Logs**\n\nHere are the latest logs."
        )
    except Exception as e:
        logger.error(f"Logs Send Error: {e}")
        await callback_query.answer("⚠️ Failed to send logs. Please check the log file manually.", show_alert=True)

    await callback_query.answer("Logs sent to your private chat.", show_alert=True)

# ✅ Back to Start Callback
@app.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start_callback(client, callback_query):
    user = callback_query.from_user

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎶 Play Music", callback_data="play_music"),
         InlineKeyboardButton("🔊 Volume", callback_data="volume_control")],
        [InlineKeyboardButton("📌 My Playlist", callback_data="my_playlist"),
         InlineKeyboardButton("🎵 Now Playing", callback_data="now_playing")],
        [InlineKeyboardButton("⚙ Settings", callback_data="settings"),
         InlineKeyboardButton("📢 Updates", url="https://t.me/RolaVibeUpdates")],
        [InlineKeyboardButton("📻 Radio", callback_data="radio")]
    ])

    # ✅ Add Owner-Specific Option
    if user.id == OWNER_ID:
        keyboard.inline_keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])

    await callback_query.edit_message_text(
        "**✨ Welcome to _Rola Vibe_! 🎶**\n\n"
        "🎧 *Enjoy high-quality music streaming in your groups.*\n"
        "🎶 *Play your favorite songs with just a command!*\n\n"
        "📌 *Join* [@RolaVibeUpdates](https://t.me/RolaVibeUpdates) *for latest updates!*\n\n"
        "👨‍💻 *Developed by* [Mr Nick](https://t.me/5620922625)",
        reply_markup=keyboard
    )

# 🔥 Run Bot
async def main():
    try:
        await ensure_files_exist()
        await load_queue()
        await load_fm_channels()
        await load_maintenance_mode()
        await app.start()
        await call_py.start()
        await idle()
    except Exception as e:
        logger.error(f"❌ Bot Startup Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
