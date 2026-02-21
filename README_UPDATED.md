# Discord Music Bot (with Queue, Search, Jingles, and Repeat)

This Discord music bot parses YouTube / YouTube Music playlists and search queries, streams audio into voice channels via FFmpeg, supports per-guild queues, and plays a radio jingle after every two songs. It also supports searching by song name, queuing, immediate play, and repeat modes.

## Highlights

- Play from YouTube playlists or single URLs
- Search by song name or artist (e.g., `!play never gonna give you up`) and queue the top result
- Per-guild queue and now-playing tracking
- `!play_now` to interrupt and play immediately
- `!skip [count]` to skip one or more songs
- `!repeat` to toggle repeating the current song
- `!repeat_playlist` to toggle repeating the last loaded playlist
- Radio jingle after every 2 songs (customizable)

## Requirements

- Python 3.10 (used in development)
- FFmpeg (installed and available in PATH)
- A virtual environment (recommended)

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Or manually:

```powershell
pip install "discord.py>=2.4.0" yt-dlp PyNaCl ffmpeg-python
```

## Configure the Bot

1. Create a bot in the Discord Developer Portal and copy the token.
2. Set `DISCORD_BOT_TOKEN` environment variable:

```powershell
$env:DISCORD_BOT_TOKEN = "your_bot_token_here"
```

3. Ensure the bot has these intents enabled:
- Message Content
- Guilds
- Voice States

## Run

```powershell
python bot.py
```

The bot prints startup info and the list of commands.

## Commands (Full)

- `!load_playlist <URL>`
  - Load a YouTube or YouTube Music playlist into the server queue.

- `!play [<URL or search terms>]`
  - If no argument: starts playback of the queued songs.
  - If given a URL: queues the song and starts playback if idle.
  - If given search terms: searches YouTube (top result) and queues it.

- `!play_now <URL or search terms>`
  - Immediately stops the current track and plays the requested song (does not clear the queue).

- `!skip [count]`
  - Stop current song and remove `count-1` songs from the front of the queue (default `count=1`).

- `!queue`
  - Shows the currently playing track and the next up to 10 songs in the queue.

- `!repeat`
  - Toggle repeating the currently playing song.

- `!repeat_playlist`
  - Toggle repeating the last loaded playlist. When enabled and the queue empties, the last playlist is re-queued and playback continues.

- `!test_jingle`
  - Connects to your channel and plays the configured jingle (or generated sine if none available).

- `!stop`
  - Clears the queue, stops playback, and disconnects the bot from voice.

## Behavior and Notes

- Queueing:
  - `!play` and search results append to the per-guild queue. If nothing is playing, `!play` starts playback immediately.
  - `!play_now` interrupts playback and plays the requested song immediately while preserving the rest of the queue.

- Repeat:
  - `!repeat` replays the same song when it finishes.
  - `!repeat_playlist` stores the last loaded playlist (from `!load_playlist`) in `last_playlist` per guild and refills the queue when it becomes empty.

- Jingle:
  - The bot plays a jingle after every 2 songs (configurable in code).
  - It prefers a custom jingle file (put `whatever_the_fucks_this_is.wav` next to `bot.py` or change the path), then Windows `tada.wav`, then a generated sine wave fallback.

- Metadata display:
  - Search results preserve title/uploader metadata when queued so `!queue` and now-playing show friendly names.

## Configuration Tips

- `jingle_path` in `MusicPlayer.__init__` points to your custom jingle file.
- `ffmpeg_stream_options` are used for streaming YouTube audio; `ffmpeg_local_options` are used for local files to avoid reconnect flags that can silence local playback.

## Troubleshooting

- Voice connection errors:
  - Make sure the bot has `Connect` and `Speak` permissions.
  - If you see encryption negotiation errors, try upgrading `discord.py` and restarting the bot.

- No audio / silent jingles:
  - Ensure FFmpeg is installed and reachable from PATH.
  - Ensure jingle file formats are supported by FFmpeg.

## Development and Testing

- Use `test_jingle()` command to validate jingle playback in your voice channel.
- For debugging, run the bot from a terminal and watch printed logs for parsing and playback operations.

## License & Support

This project is provided as-is. For upstream library issues, check:
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- discord.py: https://github.com/Rapptz/discord.py
