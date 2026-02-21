# Discord Music Bot with Radio Jingles

A Discord bot that parses YouTube and YouTube Music playlists, streams songs through voice chat, and plays a radio jingle after every 2 songs.

## Features

- 🎵 Parse YouTube and YouTube Music playlists
- 🔊 Stream audio directly to Discord voice channels
- 📻 Automatic radio jingles after every 2 songs
- 📋 Queue management with view commands
- ⏭️ Skip, stop, and playback controls
- 🎯 Per-guild queue management

## Prerequisites

- Python 3.8+
- FFmpeg (required for audio processing)
- Discord Bot Token
- A Discord server to test the bot

## Installation

### 1. Install FFmpeg

**Windows:**
```bash
# Using chocolatey
choco install ffmpeg

# Or download from https://ffmpeg.org/download.html
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or manually install:
```bash
pip install discord.py yt-dlp PyNaCl
```

### 3. Set Up Discord Bot Token

**Option A: Environment Variable (Recommended)**
```bash
# Windows (PowerShell)
$env:DISCORD_BOT_TOKEN = "your_bot_token_here"

# Windows (Command Prompt)
set DISCORD_BOT_TOKEN=your_bot_token_here

# Linux/macOS
export DISCORD_BOT_TOKEN="your_bot_token_here"
```

**Option B: Edit the bot.py file**
- Replace `'YOUR_BOT_TOKEN_HERE'` at the bottom of bot.py with your actual token

### 4. Get Your Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to "Bot" section and click "Add Bot"
4. Under TOKEN, click "Copy" to get your token
5. Enable these Intents:
   - Message Content Intent
   - Guild Members Intent
   - Voice States

## Running the Bot

```bash
python bot.py
```

The bot will start and display:
```
[+] Bot logged in as YourBotName#0000
[+] Bot is ready to use
[*] Commands: !load_playlist <URL>, !play, !skip, !queue, !stop
```

## Commands

### Load Playlist
```
!load_playlist <YouTube URL>
```
Loads a YouTube or YouTube Music playlist into the queue.

**Examples:**
- YouTube Playlist: `!load_playlist https://www.youtube.com/playlist?list=PLxxxxxx`
- YouTube Music Playlist: `!load_playlist https://music.youtube.com/playlist?list=PLxxxxxx`

### Play
```
!play
```
Starts playing the loaded playlist. You must be in a voice channel.

### Skip
```
!skip
```
Skips the current song.

### Queue
```
!queue
```
Shows the next 10 songs in the queue.

### Stop
```
!stop
```
Stops playback and disconnects the bot from the voice channel.

## How It Works

1. **Playlist Parsing**: Uses `yt-dlp` to extract song URLs from YouTube playlists
2. **Queue Management**: Songs are added to a queue per Discord server
3. **Audio Streaming**: Uses FFmpeg to stream audio through Discord voice channels
4. **Jingle System**: After every 2 songs, the bot plays a radio jingle sound before continuing
5. **Automatic Playback**: Songs play sequentially, with automatic handling of next song when current finishes

## Customizing the Jingle

By default, the bot uses Windows' built-in "tada.wav" sound. To use a custom jingle:

1. Place your audio file (MP3, WAV, etc.) in the bot directory
2. Modify the `play_jingle()` function to point to your file:

```python
jingle_path = "path/to/your/jingle.mp3"
audio_source = discord.FFmpegPCMAudio(jingle_path, **ffmpeg_options)
```

## Troubleshooting

### Bot doesn't connect to voice channel
- Ensure FFmpeg is installed and in your system PATH
- Check that the bot has permission to connect and speak in the voice channel

### Songs stop playing
- Verify your internet connection
- Check that the YouTube URL is still valid
- Some videos may be blocked due to restrictions

### "No module named discord"
```bash
pip install --upgrade discord.py
```

### FFmpeg not found
Make sure FFmpeg is installed and added to your system PATH, or specify the full path in your code.

## Notes

- The bot maintains separate queues for each Discord server
- The jingle counter resets after playing a jingle
- The bot automatically clears the queue when stopped
- Make sure your bot has the necessary permissions in your Discord server

## Support

For issues with yt-dlp: https://github.com/yt-dlp/yt-dlp
For issues with discord.py: https://github.com/Rapptz/discord.py

