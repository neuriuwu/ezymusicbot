import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import subprocess
import math
import io
from collections import deque
import random
from pathlib import Path
from dotenv import load_dotenv
import requests
import re
import functools
import aiohttp
import socket

# ISP DNS bypass for Danbooru (common in some regions)
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == 'danbooru.donmai.us':
        # Cloudflare IP for Danbooru
        return _orig_getaddrinfo('104.26.10.39', port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _custom_getaddrinfo

load_dotenv()

# Try to import config, fall back to environment variables
try:
    from config import DANBOORU_USERNAME, DANBOORU_API_KEY
except ImportError:
    DANBOORU_USERNAME = os.getenv('DANBOORU_USERNAME', '')
    DANBOORU_API_KEY = os.getenv('DANBOORU_API_KEY', '')

# Configure bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)
# Remove default help command so we can provide a custom one
bot.remove_command('help')

# YT-DLP options
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'socket_timeout': 30,
}

# FFmpeg options for streaming audio (YouTube)
ffmpeg_stream_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# FFmpeg options for local files
ffmpeg_local_options = {
    'before_options': '',
    'options': '-vn'
}

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.queue = deque()
        self.current_guild_data = {}
        self.jingle_counter = {}
        # Path to your custom jingle file - set to None to auto-detect
        self.jingle_path = "whatever_the_fucks_this_is.wav"
        # Will try: custom jingle → Windows tada.wav → generated beep
        
    def get_guild_data(self, guild_id):
        if guild_id not in self.current_guild_data:
            self.current_guild_data[guild_id] = {
                'queue': deque(),
                'current_voice_client': None,
                'playing': False,
                'jingle_count': 0,
                # Repeat controls
                'repeat_song': False,
                'repeat_playlist': False,
                # Store last loaded playlist for repeat_playlist
                'last_playlist': [],
                # Flag to prevent automatic queue play after interrupt
                'interrupt_next': False,
                'preload_task': None,
                # Per-guild jingle override (None = use global self.jingle_path)
                'guild_jingle_path': None,
                # UI state tracking
                'ui_enabled': True,
                'text_channel': None,
                'last_ui_message': None,
            }
        return self.current_guild_data[guild_id]

    async def extract_spotify_metadata(self, url):
        """Extract title and artist from a Spotify URL using HTML meta tags"""
        try:
            print(f"[*] Extracting Spotify metadata for: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            # Run requests.get in the executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, functools.partial(requests.get, url, headers=headers, timeout=10))
            
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', response.text)
            desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', response.text)
            
            title = title_match.group(1) if title_match else None
            desc = desc_match.group(1) if desc_match else None
            
            if not title:
                return None
                
            # For tracks, "Artist · Song · Year", for playlists "Playlist · Spotify · Items"
            search_query = title
            if desc and '·' in desc:
                first_part = desc.split('·')[0].strip()
                if first_part != "Playlist":
                     search_query = f"{title} {first_part}"
            
            print(f"[+] Spotify metadata extracted: {search_query}")
            return search_query
        except Exception as e:
            print(f"[!] Error extracting Spotify metadata: {e}")
            return None
            
    async def extract_spotify_playlist_tracks(self, url):
        """Extract up to 30 track URLs from a Spotify playlist/album HTML and fetch their metadata"""
        try:
            print(f"[*] Extracting Spotify playlist tracks for: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, functools.partial(requests.get, url, headers=headers, timeout=10))
            
            # Extract track URLs
            track_urls = re.findall(r'<meta name="music:song" content="([^"]+)"', response.text)
            if not track_urls:
                print("[!] No tracks found in Spotify playlist HTML")
                return []
                
            print(f"[+] Found {len(track_urls)} Spotify tracks, fetching metadata concurrently...")
            
            async def fetch_meta(session, track_url):
                try:
                    async with session.get(track_url, headers=headers) as resp:
                        text = await resp.text()
                        title_match = re.search(r'<meta property="og:title" content="([^"]+)"', text)
                        desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', text)
                        title = title_match.group(1) if title_match else None
                        desc = desc_match.group(1) if desc_match else None
                        
                        if not title:
                            return None
                            
                        search_query = title
                        if desc and '·' in desc:
                            first_part = desc.split('·')[0].strip()
                            if first_part != "Playlist":
                                 search_query = f"{title} {first_part}"
                        return search_query
                except:
                    return None

            async with aiohttp.ClientSession() as session:
                tasks = [fetch_meta(session, t_url) for t_url in track_urls]
                results = await asyncio.gather(*tasks)
                
            queries = [r for r in results if r]
            print(f"[+] Successfully resolved {len(queries)} Spotify tracks")
            return queries
        except Exception as e:
            print(f"[!] Error extracting Spotify playlist: {e}")
            return []
    
    async def parse_playlist(self, url):
        """Parse YouTube or YouTube Music playlist and extract song URLs.

        Uses a fast listing mode for playlists (extract_flat) so it doesn't
        fetch full metadata for every entry. Returns a list of song dicts.
        """
        songs = []
        
        # Check for Spotify URL
        if 'spotify.com' in url:
            if '/playlist/' in url or '/album/' in url:
                search_queries = await self.extract_spotify_playlist_tracks(url)
                if search_queries:
                    for query in search_queries:
                        songs.append({
                            'url': f"ytsearch1:{query}",
                            'title': query,
                            'duration': 0,
                            'uploader': 'Spotify Track'
                        })
                    return songs
                print("[!] Failed to extract Spotify playlist tracks")
                return []
            else:
                search_query = await self.extract_spotify_metadata(url)
                if search_query:
                    print(f"[*] Converted Spotify URL to search query: {search_query}")
                    url = f"ytsearch1:{search_query}"
                else:
                    print("[!] Failed to extract Spotify metadata")
                    return []
                
        try:
            # Fast-list options: extract only basic playlist entries
            fast_opts = ydl_opts.copy()
            fast_opts.update({'extract_flat': True, 'skip_download': True})

            print(f"[*] Parsing playlist (fast) : {url}")
            with yt_dlp.YoutubeDL(fast_opts) as ydl:
                result = ydl.extract_info(url, download=False)

            # If it's a playlist, entries will be a list of dicts with 'url' or 'id'
            if isinstance(result, dict) and result.get('entries'):
                for entry in result['entries']:
                    if not entry:
                        continue
                    # entry may be a flat entry with 'url' or 'id'
                    video_url = entry.get('url') or entry.get('id')
                    
                    # Validate and normalize the URL
                    if not video_url:
                        print(f"[!] Entry has no URL/ID: {entry}")
                        continue
                    
                    # Convert 11-char video ID to full URL
                    if isinstance(video_url, str) and len(video_url) == 11 and not video_url.startswith('http'):
                        video_url = f"https://www.youtube.com/watch?v={video_url}"
                    
                    # build a lightweight song entry; full metadata is fetched later
                    songs.append({
                        'url': video_url,
                        'title': entry.get('title', 'Unknown Title'),
                        'duration': entry.get('duration', 0),
                        'uploader': entry.get('uploader', 'Unknown Artist')
                    })
            else:
                # Single video or non-playlist
                # Use normal extraction to get proper metadata
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                songs.append({
                    'url': info.get('webpage_url', url),
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown Artist')
                })

            print(f"[+] Found {len(songs)} songs in playlist")
            return songs
        except Exception as e:
            print(f"[!] Error parsing playlist: {e}")
            return []
    
    async def get_audio_url(self, url):
        """Extract direct audio URL from YouTube video"""
        try:
            # Use yt-dlp to get formats and pick the best audio-only format
            opts = ydl_opts.copy()
            opts.update({'skip_download': True})
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Unpack ytsearch results
            if 'entries' in info and info['entries']:
                info = info['entries'][0]

            # Prefer direct format URL if available
            formats = info.get('formats') or []
            best_audio = None
            
            # Try to find audio-only format (best quality)
            if formats:
                for f in reversed(formats):
                    fcodec = f.get('acodec', 'none')
                    vcodec = f.get('vcodec', 'none')
                    if fcodec != 'none' and vcodec == 'none':
                        best_audio = f
                        break
                
                # Fallback: find any format with audio
                if not best_audio:
                    for f in reversed(formats):
                        if f.get('acodec', 'none') != 'none':
                            best_audio = f
                            break

            if best_audio and best_audio.get('url'):
                return best_audio['url']
                
            # Fallback if there are no formats but the info dictionary has a 'url' key directly
            if info.get('url') and not info.get('url').startswith('ytsearch'):
                return info['url']

            # Last fallback: return the webpage URL and let ffmpeg handle it
            result_url = info.get('webpage_url', url)
            print(f"[*] Using webpage URL for streaming: {result_url}")
            return result_url
        except Exception as e:
            print(f"[!] Error getting audio URL: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def preload_next_song(self, guild_id):
        """Background task to preload the next song's audio URL 10s before current song ends"""
        guild_data = self.get_guild_data(guild_id)
        current_song = guild_data.get('current_song')
        if not current_song:
            return
            
        # duration is in seconds
        duration = current_song.get('duration', 0)
        # Sleep until 10 seconds before the song ends
        sleep_time = max(0, duration - 10)
        if sleep_time <= 0:
            return
            
        try:
            await asyncio.sleep(sleep_time)
            
            # Wake up, check if we're still playing the same song
            if guild_data.get('current_song') != current_song or not guild_data.get('playing'):
                return
                
            # Check if there is a next song in the queue
            if not guild_data['queue']:
                # No next song to preload
                return
                
            next_song = guild_data['queue'][0]
            if 'preloaded_url' not in next_song:
                print(f"[*] Preloading audio URL for next song: {next_song.get('title')}")
                url = await self.get_audio_url(next_song['url'])
                if url:
                    next_song['preloaded_url'] = url
                    print(f"[+] Successfully preloaded: {next_song.get('title')}")
        except asyncio.CancelledError:
            # Task was cancelled (e.g., song was skipped or stopped)
            pass
        except Exception as e:
            print(f"[!] Error in preload_next_song: {e}")

    async def play_audio(self, guild_id, voice_client, audio_url, song_info):
        """Play audio in voice channel"""
        try:
            guild_data = self.get_guild_data(guild_id)
            # Track current song
            guild_data['current_song'] = song_info
            guild_data['playing'] = True
            guild_data['current_voice_client'] = voice_client
            
            # Cancel any existing preload task
            if guild_data.get('preload_task'):
                guild_data['preload_task'].cancel()
                guild_data['preload_task'] = None
                
            print(f"[*] Now playing: {song_info['title']} by {song_info['uploader']}")
            
            # Send the interactive UI dashboard
            await send_now_playing_message(guild_id)
            
            # Start a new preload task if we have a valid duration > 10s
            duration = song_info.get('duration', 0)
            if duration > 10:
                loop = self.bot.loop
                guild_data['preload_task'] = loop.create_task(self.preload_next_song(guild_id))
            
            # Use direct audio source
            audio_source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_stream_options)
            
            # Get the event loop to schedule coroutines from the after callback
            loop = self.bot.loop
            
            voice_client.play(
                audio_source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.on_song_finished(guild_id, voice_client, song_info),
                    loop
                ) if not e else asyncio.run_coroutine_threadsafe(
                    self.play_next_song(guild_id, voice_client),
                    loop
                )
            )
        except Exception as e:
            print(f"[!] Error playing audio: {e}")
    
    async def on_song_finished(self, guild_id, voice_client, song_info):
        """Called when a song finishes playing"""
        guild_data = self.get_guild_data(guild_id)
        
        # Check if this was an interrupt - if so, don't play next song
        if guild_data.get('interrupt_next'):
            print("[*] Song interrupted by play_now, waiting for new track...")
            guild_data['interrupt_next'] = False
            return
        
        if not song_info.get('skip_jingle'):
            guild_data['jingle_count'] += 1
            print(f"[+] Song finished: {song_info.get('title', 'Unknown')}")
            print(f"[+] Songs played: {guild_data['jingle_count']}")
        else:
            print(f"[+] Song finished (live): {song_info.get('title', 'Unknown')}")
            print("[*] Skipping jingle counter for live play")

        # If repeat single-song is enabled, replay the same song
        if guild_data.get('repeat_song'):
            print("[*] Repeating current song")
            # replay the same song_info
            audio_url = await self.get_audio_url(song_info['url'])
            if audio_url:
                await self.play_audio(guild_id, voice_client, audio_url, song_info)
                return
            else:
                print("[!] Could not get audio for repeated song, continuing")

        # Check if we need to play a jingle after every 2 songs
        if guild_data['jingle_count'] >= 2 and not song_info.get('skip_jingle'):
            print("[*] Playing radio jingle...")
            guild_data['jingle_count'] = 0
            # Generate a simple jingle instead of requiring a file
            await self.play_jingle(guild_id, voice_client)
        else:
            # Continue with next song in queue
            await self.play_next_song(guild_id, voice_client)
    
    async def play_jingle(self, guild_id, voice_client):
        """Play a radio jingle sound"""
        try:
            # Check voice client is still connected
            if not voice_client or not voice_client.is_connected():
                print("[!] Voice client not connected, skipping jingle")
                await asyncio.sleep(1)
                await self.play_next_song(guild_id, voice_client)
                return
            
            print("[*] Playing radio jingle...")
            audio_source = None
            
            # Try to use guild-specific jingle first, then global jingle_path
            guild_data = self.get_guild_data(guild_id)
            guild_jingle = guild_data.get('guild_jingle_path')
            jingle_candidates = [p for p in [guild_jingle, self.jingle_path] if p]
            for candidate in jingle_candidates:
                if os.path.exists(candidate):
                    print(f"[*] Using jingle: {candidate}")
                    try:
                        audio_source = discord.FFmpegPCMAudio(candidate, **ffmpeg_local_options)
                        break
                    except Exception as e:
                        print(f"[!] Error loading jingle {candidate}: {e}")
                        audio_source = None
            
            # Try Windows built-in tada.wav
            if not audio_source:
                windows_jingle = "C:/Windows/Media/tada.wav"
                if os.path.exists(windows_jingle):
                    print(f"[*] Using Windows jingle: {windows_jingle}")
                    try:
                        audio_source = discord.FFmpegPCMAudio(windows_jingle, **ffmpeg_local_options)
                    except Exception as e:
                        print(f"[!] Error loading Windows jingle: {e}")
                        audio_source = None
            
            # Generate a simple beep jingle using FFmpeg as fallback
            if not audio_source:
                print("[*] Generating beep jingle...")
                audio_source = self.create_sine_wave()
            
            # If we still don't have audio, skip the jingle
            if not audio_source:
                print("[!] Could not create/load jingle, skipping...")
                await asyncio.sleep(1)
                await self.play_next_song(guild_id, voice_client)
                return
            
            # Check voice client is STILL connected before playing
            if not voice_client or not voice_client.is_connected():
                print("[!] Voice client disconnected before playback, skipping jingle")
                await asyncio.sleep(1)
                await self.play_next_song(guild_id, voice_client)
                return
            
            # Get the event loop to schedule coroutines from the after callback
            loop = self.bot.loop
            
            print("[*] Starting jingle playback...")
            voice_client.play(
                audio_source,
                after=lambda e: (
                    print(f"[!] Jingle playback error: {e}") if e else print("[+] Jingle finished"),
                    asyncio.run_coroutine_threadsafe(
                        self.play_next_song(guild_id, voice_client),
                        loop
                    )
                )
            )
        except Exception as e:
            print(f"[!] Error in play_jingle: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(1)
            await self.play_next_song(guild_id, voice_client)
    
    def create_sine_wave(self):
        """Create a simple sine wave audio source for jingle"""
        try:
            print("[*] Generating sine wave jingle...")
            # Create a temporary WAV file with a sine wave
            temp_jingle = "temp_jingle.wav"
            
            # Use FFmpeg to generate a sine wave and save to temp file
            result = subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=2',
                '-acodec', 'pcm_s16le', '-ar', '48000', '-ac', '2', 
                '-y', temp_jingle
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            
            if result.returncode != 0:
                print("[!] FFmpeg failed to generate sine wave")
                return None
            
            if not os.path.exists(temp_jingle):
                print("[!] Sine wave file not created")
                return None
            
            # Load and return the audio
            print("[*] Playing generated sine wave jingle...")
            return discord.FFmpegPCMAudio(temp_jingle, **ffmpeg_local_options)
            
        except subprocess.TimeoutExpired:
            print("[!] FFmpeg timeout while generating sine wave")
            return None
        except Exception as e:
            print(f"[!] Error creating sine wave: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def play_next_song(self, guild_id, voice_client):
        """Play the next song in queue"""
        guild_data = self.get_guild_data(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            guild_data['playing'] = False
            return
        
        if guild_data['queue']:
            song = guild_data['queue'].popleft()

            # Use preloaded URL if available (fetched 10s before end of previous track)
            audio_url = song.pop('preloaded_url', None)
            if audio_url:
                print(f"[*] Using preloaded audio for: {song['title']}")
            else:
                print(f"[*] Getting audio URL for: {song['title']}")
                audio_url = await self.get_audio_url(song['url'])

            if audio_url:
                await self.play_audio(guild_id, voice_client, audio_url, song)
            else:
                print(f"[!] Could not get audio for {song['title']}, skipping...")
                await self.play_next_song(guild_id, voice_client)
        else:
            # If repeat_playlist is enabled and we have a last playlist, refill the queue
            if guild_data.get('repeat_playlist') and guild_data.get('last_playlist'):
                print("[*] Repeating playlist: refilling queue")
                for s in guild_data['last_playlist']:
                    # copy dicts to avoid shared references
                    guild_data['queue'].append(s.copy() if isinstance(s, dict) else s)
                # Play the next song now
                await self.play_next_song(guild_id, voice_client)
                return

            guild_data['playing'] = False
            guild_data['current_song'] = None
            print("[*] Queue empty, stopping playback")
            if voice_client.is_playing():
                voice_client.stop()

# Initialize music player
music_player = MusicPlayer(bot)

class QueueSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        guild_data = music_player.get_guild_data(guild_id)
        queue = list(guild_data['queue'])[:25]
        
        if not queue:
            options = [discord.SelectOption(label="Queue is empty", value="empty")]
            super().__init__(placeholder="Select a song to skip to...", min_values=1, max_values=1, options=options, disabled=True)
            return

        options = []
        for i, song in enumerate(queue):
            label = f"{i+1}. {song['title']}"[:100]
            options.append(discord.SelectOption(label=label, value=str(i+1)))
            
        super().__init__(placeholder="Select a song to skip to...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "empty":
            return
            
        # The value is 1-indexed based on how we appended it.
        # But wait, index logic:
        # User clicks "3. Song C", value="3".
        # This means we must pop 2 songs to make "Song C" the next in queue (`index-1`).
        skips = int(self.values[0])
        guild_data = music_player.get_guild_data(self.guild_id)
        
        for _ in range(skips - 1):
            if guild_data['queue']:
                guild_data['queue'].popleft()
                
        await interaction.response.defer()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            voice_client.stop() # Triggers the next song


class MusicControlView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(QueueSelect(guild_id))

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.red, custom_id="music_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_data = music_player.get_guild_data(self.guild_id)
        guild_data['queue'].clear()
        if guild_data.get('preload_task'):
            guild_data['preload_task'].cancel()
            guild_data['preload_task'] = None
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            guild_data['playing'] = False
            guild_data['current_song'] = None

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="music_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        guild_data = music_player.get_guild_data(self.guild_id)
        current = guild_data.get('current_song')
        if current and voice_client:
            guild_data['queue'].appendleft(current)
            voice_client.stop()

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="music_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client:
            if voice_client.is_paused():
                voice_client.resume()
                button.emoji = "⏸️"
            elif voice_client.is_playing():
                voice_client.pause()
                button.emoji = "▶️"
            await interaction.message.edit(view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            voice_client.stop()

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="music_shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild_data = music_player.get_guild_data(self.guild_id)
        if guild_data['queue']:
            temp_list = list(guild_data['queue'])
            random.shuffle(temp_list)
            guild_data['queue'] = deque(temp_list)
            
        # Re-render the view so the dropdown updates with the new order
        await interaction.message.edit(view=MusicControlView(self.guild_id))

async def send_now_playing_message(guild_id):
    guild_data = music_player.get_guild_data(guild_id)
    if not guild_data.get('ui_enabled', True):
        return

    channel = guild_data.get('text_channel')
    if not channel:
        return

    # Delete previous message if it exists
    last_msg = guild_data.get('last_ui_message')
    if last_msg:
        try:
            await last_msg.delete()
        except:
            pass

    song = guild_data.get('current_song')
    if not song:
        return

    duration = song.get('duration', 0)
    minutes, seconds = divmod(duration, 60)
    duration_str = f"{minutes:02d}:{seconds:02d}"

    queue_len = len(guild_data['queue'])
    requester = song.get('requester', 'Unknown')
    
    # Check if voice_client is connected
    try:
        voice_client = discord.utils.get(bot.voice_clients, guild=channel.guild)
        room_name = voice_client.channel.name if voice_client and voice_client.channel else "Unknown"
    except:
        room_name = "Unknown"

    embed = discord.Embed(
        title=song['title'],
        url=song['url'],
        color=discord.Color.from_rgb(255, 105, 180) # Pink
    )
    embed.set_author(name="Zani Music Room", icon_url=bot.user.display_avatar.url if bot.user else None)
    
    # Format fields
    desc = f"⭐ **Author:**\n┗ {song['uploader'][:20]}\n\n"
    desc += f"🕒 **Duration:**\n┗ {duration_str}\n\n"
    desc += f"💬 **Queues:**\n┗ {queue_len}\n\n"
    desc += f"👤 **Requester:**\n┗ {requester}\n\n"
    desc += f"🎧 **Room:**\n┗ {room_name}\n\n"
    desc += f"👑 **Support:**\n┗ Zani\n"
    
    embed.description = desc

    # Try to attach a local banner image if it exists
    file = None
    if os.path.exists("zanibanner.jpg"):
        file = discord.File("zanibanner.jpg", filename="zanibanner.jpg")
        embed.set_image(url="attachment://zanibanner.jpg")

    view = MusicControlView(guild_id)
    
    try:
        if file:
            msg = await channel.send(embed=embed, file=file, view=view)
        else:
            msg = await channel.send(embed=embed, view=view)
        guild_data['last_ui_message'] = msg
    except Exception as e:
        print(f"[!] Error sending UI message: {e}")

@bot.event
async def on_ready():
    print(f'[+] Bot logged in as {bot.user}')
    print(f'[+] Bot is ready to use')

@bot.command(name='load_playlist', help='Load a YouTube playlist. Usage: !load_playlist <URL>')
async def load_playlist(ctx, *, url):
    """Load a YouTube or YouTube Music playlist"""
    print(f"\n[*] User {ctx.author} loading playlist: {url}")
    
    
    guild_data = music_player.get_guild_data(ctx.guild.id)
    guild_data['text_channel'] = ctx.channel
    
    # Parse the playlist
    songs = await music_player.parse_playlist(url)
    
    if not songs:
        embed = discord.Embed(
            title="❌ Error",
            description="Could not parse the playlist. Make sure the URL is valid.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    
    # Add songs to queue
    for song in songs:
        song['requester'] = ctx.author.display_name
        guild_data['queue'].append(song)
    # Save last playlist for repeat functionality
    guild_data['last_playlist'] = list(songs)
    
    embed = discord.Embed(
        title="✅ Playlist Loaded",
        description=f"Added {len(songs)} songs to the queue",
        color=discord.Color.green()
    )
    embed.add_field(name="First Song", value=songs[0]['title'], inline=False)
    embed.add_field(name="Queue Size", value=str(len(guild_data['queue'])), inline=False)
    await ctx.send(embed=embed)
    
    # Start playing if not already playing
    if not guild_data['playing']:
        await play_queue(ctx)

@bot.command(name='play', help='Play the queued songs or a single URL/song. Usage: !play [<URL/song name>]')
async def play_queue(ctx, *, url: str = None):
    """Start playing the queue or play a specific song by URL or search query"""
    await _play_core(ctx, url=url, skip_jingle=False)

@bot.command(name='live_play', help='Play a playlist in live concert mode (no jingles). Usage: !live_play <playlist URL>')
async def live_play_queue(ctx, *, url: str):
    """Load and play a playlist without any jingle interruptions, like a live concert"""
    print(f"\n[*] User {ctx.author} started live playlist: {url}")

    # Must be in a voice channel
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            title="❌ Error",
            description="You must be in a voice channel to play music",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    voice_channel = ctx.author.voice.channel

    # Connect (re-use existing or make new connection)
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(title="❌ Connection Timeout", description="Couldn't connect to voice channel.", color=discord.Color.red()))
            return
        except discord.ClientException:
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        except Exception as e:
            await ctx.send(embed=discord.Embed(title="❌ Connection Error", description=str(e), color=discord.Color.red()))
            return

    parsing_embed = discord.Embed(
        title="🎸 Loading Live Playlist...",
        description=f"Parsing: {url}",
        color=discord.Color.orange()
    )
    msg = await ctx.send(embed=parsing_embed)

    songs = await music_player.parse_playlist(url)
    if not songs:
        await msg.edit(embed=discord.Embed(
            title="❌ Error",
            description="Could not load playlist. Make sure the URL is a valid YouTube/YouTube Music playlist.",
            color=discord.Color.red()
        ))
        return

    # Mark all songs as skip_jingle
    for song in songs:
        song['skip_jingle'] = True

    guild_data = music_player.get_guild_data(ctx.guild.id)
    guild_data['text_channel'] = ctx.channel

    # Stop current playback and clear queue
    if guild_data.get('preload_task'):
        guild_data['preload_task'].cancel()
        guild_data['preload_task'] = None
    if voice_client.is_playing():
        voice_client.stop()
    guild_data['queue'].clear()

    for song in songs:
        song['requester'] = ctx.author.display_name
        guild_data['queue'].append(song)
    guild_data['last_playlist'] = list(songs)
    guild_data['jingle_count'] = 0

    await msg.edit(embed=discord.Embed(
        title="🎸 Live Concert Mode",
        description=f"Loaded **{len(songs)}** songs — no jingles, pure music 🎶",
        color=discord.Color.orange()
    ).add_field(name="First Track", value=songs[0]['title'], inline=False))

    await music_player.play_next_song(ctx.guild.id, voice_client)

async def _play_core(ctx, url: str = None, skip_jingle: bool = False):
    """Core playback logic for play and live_play commands"""
    print(f"\n[*] User {ctx.author} started playback")
    
    guild_data = music_player.get_guild_data(ctx.guild.id)
    guild_data['text_channel'] = ctx.channel
    
    # Check if user is in voice channel
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            title="❌ Error",
            description="You must be in a voice channel to play music",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    voice_channel = ctx.author.voice.channel
    
    # Connect to voice channel with timeout and retry logic
    voice_client = None
    max_retries = 2
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"[*] Attempting to connect to voice channel: {voice_channel.name} (attempt {retry_count + 1}/{max_retries})")
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
            print(f"[+] Successfully connected to voice channel")
            break
        except asyncio.TimeoutError:
            retry_count += 1
            if retry_count >= max_retries:
                embed = discord.Embed(
                    title="❌ Connection Timeout",
                    description="Voice connection took too long. Try again or check bot permissions.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                print("[!] Voice connection timeout after retries")
                return
            print(f"[!] Connection timeout, retrying... ({retry_count}/{max_retries})")
            await asyncio.sleep(1)
        except discord.ClientException as e:
            # Already connected
            print(f"[*] Already connected to voice, reusing connection")
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
            if not voice_client:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"Could not connect to voice channel: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            break
        except IndexError as e:
            # Handle discord.py voice encryption mode error (server not providing modes)
            retry_count += 1
            if retry_count >= max_retries:
                embed = discord.Embed(
                    title="❌ Voice Connection Error",
                    description="Unable to negotiate voice encryption modes with server. This may be a Discord server issue. Try restarting the bot or joining a different voice channel.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                print(f"[!] Voice encryption mode error after {max_retries} attempts: {e}")
                return
            print(f"[!] Voice encryption negotiation failed, retrying... ({retry_count}/{max_retries})")
            await asyncio.sleep(2)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Connection Error",
                description=f"Failed to connect: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            print(f"[!] Voice connection error: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # If user provided a URL or search query, play that song immediately
    if url:
        print(f"[*] Play command received: {url}")
        
        # Check if it's a URL or a search query
        is_url = url.startswith(('http://', 'https://', 'www.', 'youtube.com', 'youtu.be', 'music.youtube.com'))
        
        song = None
        if not is_url:
            # It's a search query - search for the song
            print(f"[*] Searching for: {url}")
            embed = discord.Embed(
                title="🔍 Searching",
                description=f"Searching for: {url}",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            
            # Use yt-dlp to search
            try:
                opts = ydl_opts.copy()
                opts.update({'skip_download': True, 'default_search': 'ytsearch'})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                
                if not info or 'entries' not in info or not info['entries']:
                    embed = discord.Embed(
                        title="❌ No Results",
                        description=f"Could not find any songs matching: {url}",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Get the first result and preserve metadata
                first_result = info['entries'][0]
                song_url = first_result.get('url') or first_result.get('webpage_url')
                if not song_url:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Could not extract URL from search result",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Create song dict with search result metadata
                song = {
                    'url': song_url,
                    'title': first_result.get('title', 'Unknown Title'),
                    'duration': first_result.get('duration', 0),
                    'uploader': first_result.get('uploader', 'Unknown Artist'),
                    'skip_jingle': skip_jingle,
                    'requester': ctx.author.display_name
                }
                print(f"[+] Found: {song['title']} by {song['uploader']}")
            except Exception as e:
                print(f"[!] Error searching for song: {e}")
                embed = discord.Embed(
                    title="❌ Search Error",
                    description=f"Error searching YouTube: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
        else:
            # It's a URL - parse it normally
            songs = await music_player.parse_playlist(url)
            if not songs:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Could not parse the provided URL.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            song = songs[0]
            song['requester'] = ctx.author.display_name
            if skip_jingle:
                song['skip_jingle'] = True
        
        # Now we have the song, add to queue and start playback if idle
        if song:
            guild_data['queue'].append(song)
            
            # Only send basic text if UI is disabled, otherwise let the dashboard handle it
            if not guild_data.get('ui_enabled', True):
                embed = discord.Embed(
                    title="✅ Added to Queue",
                    description=f"Queued: {song['title']}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Position", value=str(len(guild_data['queue'])), inline=False)
                await ctx.send(embed=embed)

            # Save single-song as last_playlist if queue was empty before (so repeat_playlist can use it)
            if not guild_data.get('last_playlist'):
                guild_data['last_playlist'] = [song]

            # If nothing is currently playing, start playback
            if not guild_data.get('playing'):
                guild_data['jingle_count'] = 0
                await music_player.play_next_song(ctx.guild.id, voice_client)
            return

    if not guild_data['queue']:
        embed = discord.Embed(
            title="⚠️ Empty Queue",
            description="Load a playlist first using !load_playlist <URL>",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return

    if not url and skip_jingle:
        for s in guild_data['queue']:
            if isinstance(s, dict):
                s['skip_jingle'] = True

    # Start playing queue
    guild_data['jingle_count'] = 0
    if not guild_data.get('ui_enabled', True):
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"Starting playback of {len(guild_data['queue'])} songs",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    await music_player.play_next_song(ctx.guild.id, voice_client)


@bot.command(name='play_now', help='Play a URL or search immediately, interrupting current playback')
async def play_now(ctx, *, query: str):
    """Play the provided URL or search query immediately (stop current track)."""
    print(f"\n[*] User {ctx.author} requested immediate play: {query}")
    guild_data = music_player.get_guild_data(ctx.guild.id)

    # Check if user is in voice channel
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            title="❌ Error",
            description="You must be in a voice channel to play music",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    voice_channel = ctx.author.voice.channel

    # Connect to voice channel with timeout and retry logic
    voice_client = None
    max_retries = 2
    retry_count = 0
    while retry_count < max_retries:
        try:
            print(f"[*] Attempting to connect to voice channel: {voice_channel.name} (attempt {retry_count + 1}/{max_retries})")
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
            print(f"[+] Successfully connected to voice channel")
            break
        except asyncio.TimeoutError:
            retry_count += 1
            if retry_count >= max_retries:
                embed = discord.Embed(
                    title="❌ Connection Timeout",
                    description="Voice connection took too long. Try again or check bot permissions.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                print("[!] Voice connection timeout after retries")
                return
            print(f"[!] Connection timeout, retrying... ({retry_count}/{max_retries})")
            await asyncio.sleep(1)
        except discord.ClientException as e:
            # Already connected
            print(f"[*] Already connected to voice, reusing connection")
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
            if not voice_client:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"Could not connect to voice channel: {str(e)}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            break
        except Exception as e:
            embed = discord.Embed(
                title="❌ Connection Error",
                description=f"Failed to connect: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            print(f"[!] Voice connection error: {e}")
            import traceback
            traceback.print_exc()
            return

    # Determine if query is a URL or search
    is_url = query.startswith(('http://', 'https://', 'www.', 'youtube.com', 'youtu.be', 'music.youtube.com'))
    song = None
    if not is_url:
        # Search YouTube
        print(f"[*] Searching for immediate play: {query}")
        try:
            opts = ydl_opts.copy()
            opts.update({'skip_download': True, 'default_search': 'ytsearch'})
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
            if not info or 'entries' not in info or not info['entries']:
                embed = discord.Embed(
                    title="❌ No Results",
                    description=f"Could not find any songs matching: {query}",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            first_result = info['entries'][0]
            song_url = first_result.get('url') or first_result.get('webpage_url')
            if not song_url:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Could not extract URL from search result",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            song = {
                'url': song_url,
                'title': first_result.get('title', 'Unknown Title'),
                'duration': first_result.get('duration', 0),
                'uploader': first_result.get('uploader', 'Unknown Artist'),
                'requester': ctx.author.display_name
            }
        except Exception as e:
            print(f"[!] Error searching for immediate play: {e}")
            embed = discord.Embed(
                title="❌ Search Error",
                description=f"Error searching YouTube: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
    else:
        # Parse URL normally
        songs = await music_player.parse_playlist(query)
        if not songs:
            embed = discord.Embed(
                title="❌ Error",
                description="Could not parse the provided URL.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        song = songs[0]
        song['requester'] = ctx.author.display_name

    # We have a song; play it immediately
    try:
        # Set interrupt flag to prevent automatic queue continuation
        guild_data['interrupt_next'] = True
        print("[*] Interrupt flag set")
        
        # Stop current playback but do not clear the queue
        try:
            if voice_client.is_playing():
                print("[*] Stopping current playback for play_now...")
                voice_client.stop()
        except Exception as e:
            print(f"[!] Error stopping current playback: {e}")

        print(f"[*] Getting audio URL for: {query}")
        audio_url = await music_player.get_audio_url(song['url'])
        if not audio_url:
            guild_data['interrupt_next'] = False
            embed = discord.Embed(
                title="❌ Error",
                description="Could not retrieve audio for the URL.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Update last_playlist to this single song for repeat_playlist convenience
        guild_data['last_playlist'] = [song]
        guild_data['jingle_count'] = 0
        # DON'T reset interrupt_next here - let on_song_finished do it after the callback fires

        if not guild_data.get('ui_enabled', True):
            embed = discord.Embed(
                title="🎵 Now Playing (Immediate)",
                description=f"Playing: {song['title']} by {song['uploader']}",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            
        print(f"[*] Starting immediate playback of: {song['title']}")
        await music_player.play_audio(ctx.guild.id, voice_client, audio_url, song)
    except Exception as e:
        print(f"[!] Error in play_now: {e}")
        guild_data['interrupt_next'] = False
        embed = discord.Embed(
            title="❌ Error",
            description=f"Error playing now: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='skip', help='Skip songs. Usage: !skip [count]')
async def skip(ctx, count: int = 1):
    """Skip the current song and optionally more songs from the queue"""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    guild_data = music_player.get_guild_data(ctx.guild.id)
    
    # Validate count
    if count < 1:
        embed = discord.Embed(
            title="❌ Invalid Count",
            description="Skip count must be at least 1",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if not voice_client or not voice_client.is_playing():
        embed = discord.Embed(
            title="⚠️ Not Playing",
            description="No song is currently playing",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    # Remove songs from queue (count - 1 because we stop current, which plays next)
    songs_removed = 0
    for _ in range(min(count - 1, len(guild_data['queue']))):
        guild_data['queue'].popleft()
        songs_removed += 1

    # Cancel preload task so next song gets a fresh preload from its own timing
    if guild_data.get('preload_task'):
        guild_data['preload_task'].cancel()
        guild_data['preload_task'] = None

    # Clear preloaded url from songs shifted out of position
    if guild_data['queue'] and isinstance(guild_data['queue'][0], dict):
        guild_data['queue'][0].pop('preloaded_url', None)

    # Stop current song to trigger play_next_song
    voice_client.stop()
    
    if count == 1:
        embed = discord.Embed(
            title="⏭️ Skipped",
            description="Skipped to next song",
            color=discord.Color.blue()
        )
    else:
        embed = discord.Embed(
            title="⏭️ Skipped",
            description=f"Skipped {count} song(s)",
            color=discord.Color.blue()
        )
        if songs_removed > 0:
            embed.add_field(name="Removed from Queue", value=f"{songs_removed} song(s)", inline=False)
    
    await ctx.send(embed=embed)


@bot.command(name='repeat', help='Toggle repeating the current song')
async def repeat(ctx):
    """Toggle repeat for the current song"""
    guild_data = music_player.get_guild_data(ctx.guild.id)
    guild_data['repeat_song'] = not guild_data.get('repeat_song', False)
    status = "enabled" if guild_data['repeat_song'] else "disabled"
    embed = discord.Embed(
        title="🔁 Repeat Song",
        description=f"Repeat current song {status}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@bot.command(name='repeat_playlist', help='Toggle repeating the last loaded playlist')
async def repeat_playlist(ctx):
    """Toggle repeat for the last loaded playlist"""
    guild_data = music_player.get_guild_data(ctx.guild.id)
    guild_data['repeat_playlist'] = not guild_data.get('repeat_playlist', False)
    status = "enabled" if guild_data['repeat_playlist'] else "disabled"
    embed = discord.Embed(
        title="🔁 Repeat Playlist",
        description=f"Repeat playlist {status}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='queue', help='Show the current queue')
async def show_queue(ctx):
    """Display current queue"""
    guild_data = music_player.get_guild_data(ctx.guild.id)
    # Build embed showing currently playing + next items
    current = guild_data.get('current_song')
    q = list(guild_data['queue'])

    if not current and not q:
        embed = discord.Embed(
            title="📋 Queue",
            description="Queue is empty",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(title="📋 Current Queue", color=discord.Color.blue())

    if current:
        cur_title = current.get('title', 'Unknown Title')
        cur_uploader = current.get('uploader', 'Unknown')
        embed.add_field(name="Now Playing", value=f"{cur_title} — {cur_uploader}", inline=False)

    if q:
        # Show next up to 10 songs
        queue_list = []
        for i, song in enumerate(q[:10], 1):
            title = song.get('title', 'Unknown Title')
            uploader = song.get('uploader', 'Unknown')
            queue_list.append(f"{i}. {title} — {uploader}")
        description = "\n".join(queue_list)
        if len(q) > 10:
            description += f"\n... and {len(q) - 10} more songs"
        embed.add_field(name="Up Next", value=description, inline=False)

    embed.add_field(name="Total In Queue", value=str(len(q)), inline=False)
    await ctx.send(embed=embed)

@bot.command(name='stop', help='Stop playback and disconnect from voice')
async def stop(ctx):
    """Stop playback and disconnect"""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    guild_data = music_player.get_guild_data(ctx.guild.id)
    
    if voice_client and voice_client.is_connected():
        guild_data['playing'] = False
        guild_data['queue'].clear()
        if guild_data.get('preload_task'):
            guild_data['preload_task'].cancel()
            guild_data['preload_task'] = None
        voice_client.stop()
        await voice_client.disconnect()
        
        embed = discord.Embed(
            title="⏹️ Stopped",
            description="Playback stopped and disconnected from voice channel",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="⚠️ Not Connected",
            description="Bot is not in a voice channel",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

@bot.command(name='test_jingle', help='Test the jingle sound')
async def test_jingle(ctx):
    """Test jingle playback without waiting for songs"""
    print(f"\n[*] User {ctx.author} testing jingle")
    
    # Check if user is in voice channel
    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(
            title="❌ Error",
            description="You must be in a voice channel to test the jingle",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    voice_channel = ctx.author.voice.channel
    
    # Connect to voice channel with timeout and retry logic
    voice_client = None
    max_retries = 2
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"[*] Connecting to voice for jingle test...")
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
            break
        except asyncio.TimeoutError:
            retry_count += 1
            if retry_count >= max_retries:
                embed = discord.Embed(
                    title="❌ Connection Timeout",
                    description="Voice connection took too long.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            print(f"[!] Connection timeout, retrying... ({retry_count}/{max_retries})")
            await asyncio.sleep(1)
        except discord.ClientException:
            # Already connected
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
            if voice_client:
                break
            print(f"[!] Not connected and can't connect")
            embed = discord.Embed(
                title="❌ Connection Error",
                description="Could not connect to voice channel.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        except IndexError as e:
            # Handle discord.py voice encryption mode error
            retry_count += 1
            if retry_count >= max_retries:
                embed = discord.Embed(
                    title="❌ Voice Connection Error",
                    description="Unable to negotiate voice encryption modes with server.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                print(f"[!] Voice encryption mode error: {e}")
                return
            print(f"[!] Voice encryption negotiation failed, retrying... ({retry_count}/{max_retries})")
            await asyncio.sleep(2)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Connection Error",
                description=f"Failed to connect: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
    
    # Send feedback
    embed = discord.Embed(
        title="🔊 Testing Jingle",
        description="Playing jingle sound...",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    
    # Play the jingle directly
    try:
        print("[*] Playing test jingle...")
        audio_source = None
        
        # Try to use custom jingle if set
        if music_player.jingle_path and os.path.exists(music_player.jingle_path):
            print(f"[*] Using custom jingle: {music_player.jingle_path}")
            try:
                audio_source = discord.FFmpegPCMAudio(music_player.jingle_path, **ffmpeg_local_options)
            except Exception as e:
                print(f"[!] Error loading custom jingle: {e}")
                audio_source = None
        
        # Try Windows built-in tada.wav
        if not audio_source:
            windows_jingle = "whatever_the_fucks_this_is.wav"  # Change this to the actual path if you want to test it
            if os.path.exists(windows_jingle):
                print(f"[*] Using Windows jingle: {windows_jingle}")
                try:
                    audio_source = discord.FFmpegPCMAudio(windows_jingle, **ffmpeg_local_options)
                except Exception as e:
                    print(f"[!] Error loading jingle: {e}")
                    audio_source = None
        
        # Generate a simple beep jingle using FFmpeg as fallback
        if not audio_source:
            print("[*] Generating beep jingle...")
            audio_source = music_player.create_sine_wave()
        
        # If we still don't have audio, error out
        if not audio_source:
            print("[!] Could not create/load jingle")
            embed = discord.Embed(
                title="❌ Error",
                description="Could not load or generate jingle audio.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Check voice client is connected before playing
        if not voice_client or not voice_client.is_connected():
            print("[!] Voice client disconnected")
            embed = discord.Embed(
                title="❌ Error",
                description="Voice client disconnected.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        print("[*] Starting jingle playback...")
        voice_client.play(
            audio_source,
            after=lambda e: print(f"[!] Jingle error: {e}") if e else print("[+] Jingle finished")
        )
        
    except Exception as e:
        print(f"[!] Error testing jingle: {e}")
        import traceback
        traceback.print_exc()
        embed = discord.Embed(
            title="❌ Error",
            description=f"Error playing jingle: {e}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)


MIDNIGHT_PODCAST_URL = 'https://youtube.com/playlist?list=PLkJ-t-Cn6PgpZMxUqPcaicMcCdp-B5Sal&si=sjfiIYtKZXR6S0re'
MIDNIGHT_PODCAST_JINGLE = 'stupid ass jingle.wav'

@bot.command(name='midnight_podcast', help='Load and play the Midnight Podcast playlist with its own jingle')
async def midnight_podcast(ctx):
    """Load the Midnight Podcast playlist and play it with the custom midnight jingle"""
    print(f"\n[*] User {ctx.author} started Midnight Podcast")

    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(title="❌ Error", description="You must be in a voice channel", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    voice_channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(title="❌ Connection Timeout", description="Couldn't connect to voice channel.", color=discord.Color.red()))
            return
        except discord.ClientException:
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        except Exception as e:
            await ctx.send(embed=discord.Embed(title="❌ Connection Error", description=str(e), color=discord.Color.red()))
            return

    msg = await ctx.send(embed=discord.Embed(
        title="🌙 Loading Midnight Podcast...",
        description="Parsing playlist, give me a sec...",
        color=discord.Color.dark_blue()
    ))

    songs = await music_player.parse_playlist(MIDNIGHT_PODCAST_URL)
    if not songs:
        await msg.edit(embed=discord.Embed(title="❌ Error", description="Could not load playlist.", color=discord.Color.red()))
        return

    guild_data = music_player.get_guild_data(ctx.guild.id)

    # Stop current playback and clear queue
    if guild_data.get('preload_task'):
        guild_data['preload_task'].cancel()
        guild_data['preload_task'] = None
    if voice_client.is_playing():
        voice_client.stop()
    guild_data['queue'].clear()

    # Set the guild-specific jingle to the midnight podcast jingle
    if os.path.exists(MIDNIGHT_PODCAST_JINGLE):
        guild_data['guild_jingle_path'] = MIDNIGHT_PODCAST_JINGLE
        print(f"[*] Set midnight podcast jingle: {MIDNIGHT_PODCAST_JINGLE}")
    else:
        print(f"[!] Midnight podcast jingle not found: {MIDNIGHT_PODCAST_JINGLE}")
        guild_data['guild_jingle_path'] = None

    for song in songs:
        guild_data['queue'].append(song)
    guild_data['last_playlist'] = list(songs)
    guild_data['jingle_count'] = 0

    jingle_status = "🎵 with custom midnight jingle" if guild_data['guild_jingle_path'] else "(jingle file not found)"
    await msg.edit(embed=discord.Embed(
        title="🌙 Midnight Podcast",
        description=f"Loaded **{len(songs)}** tracks — {jingle_status}",
        color=discord.Color.dark_blue()
    ).add_field(name="First Track", value=songs[0]['title'], inline=False))

    await music_player.play_next_song(ctx.guild.id, voice_client)


THAIRMX_URL = 'https://music.youtube.com/playlist?list=PLx8ySUb3nuR0S8BiYrAatu14F0Ojqjf32&si=Q6FDpHCd9-iclJ3B'
THAIRMX_JINGLE = 'thairmxjing.wav'

@bot.command(name='thairmx', help='Load and play Thai Remix playlist with its own jingle')
async def thairmx(ctx):
    """Load the Thai Remix playlist and play it with the custom thairmx jingle"""
    print(f"\n[*] User {ctx.author} started Thai Remix")

    if not ctx.author.voice or not ctx.author.voice.channel:
        embed = discord.Embed(title="❌ Error", description="You must be in a voice channel", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    voice_channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
        except asyncio.TimeoutError:
            await ctx.send(embed=discord.Embed(title="❌ Connection Timeout", description="Couldn't connect to voice channel.", color=discord.Color.red()))
            return
        except discord.ClientException:
            voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        except Exception as e:
            await ctx.send(embed=discord.Embed(title="❌ Connection Error", description=str(e), color=discord.Color.red()))
            return

    msg = await ctx.send(embed=discord.Embed(
        title="🎵 Loading Thai Remix...",
        description="Parsing playlist, give me a sec...",
        color=discord.Color.from_rgb(255, 50, 100)
    ))

    songs = await music_player.parse_playlist(THAIRMX_URL)
    if not songs:
        await msg.edit(embed=discord.Embed(title="❌ Error", description="Could not load playlist.", color=discord.Color.red()))
        return

    guild_data = music_player.get_guild_data(ctx.guild.id)

    # Stop current playback and clear queue
    if guild_data.get('preload_task'):
        guild_data['preload_task'].cancel()
        guild_data['preload_task'] = None
    if voice_client.is_playing():
        voice_client.stop()
    guild_data['queue'].clear()

    # Set guild-specific jingle to thairmx jingle
    if os.path.exists(THAIRMX_JINGLE):
        guild_data['guild_jingle_path'] = THAIRMX_JINGLE
        print(f"[*] Set thairmx jingle: {THAIRMX_JINGLE}")
    else:
        print(f"[!] Thairmx jingle not found: {THAIRMX_JINGLE}")
        guild_data['guild_jingle_path'] = None

    for song in songs:
        guild_data['queue'].append(song)
    guild_data['last_playlist'] = list(songs)
    guild_data['jingle_count'] = 0

    jingle_status = "🎵 with Thai Remix jingle" if guild_data['guild_jingle_path'] else "(jingle file not found)"
    await msg.edit(embed=discord.Embed(
        title="🎵 Thai Remix",
        description=f"Loaded **{len(songs)}** tracks — {jingle_status}",
        color=discord.Color.from_rgb(255, 50, 100)
    ).add_field(name="First Track", value=songs[0]['title'], inline=False))

    await music_player.play_next_song(ctx.guild.id, voice_client)


@bot.command(name='help', help='Show full command help')
async def show_help(ctx):
    # Create embed with banner
    embed = discord.Embed(
        title="🎵 Discord Music Bot - Commands",
        description="Full list of available commands for the music bot.",
        color=discord.Color.purple()
    )
    
    # Try to load local banner image
    banner_path = "zanibanner.jpg"  # Change this to your banner filename
    if os.path.exists(banner_path):
        embed.set_image(url=f"attachment://{banner_path}")
        file = discord.File(banner_path, filename=banner_path)
    else:
        # Fallback: use a URL if local file not found
        embed.set_image(url="https://media.discordapp.net/attachments/1234567890/1234567890/banner.png")
        file = None
    
    # ── Playlist / Station commands ──────────────────────────────────
    embed.add_field(
        name="🎶 Playlist & Stations",
        value=(
            "**!load_playlist <URL>** — Load a YouTube/YT Music playlist into the queue\n"
            "**!play [URL or search]** — Start queue, queue a URL, or search & queue a song\n"
            "**!play_now <URL or search>** — Immediately play a song, interrupting current track\n"
            "**!live_play <playlist URL>** — Load & play a playlist in **live concert mode** (no jingles)\n"
            "**!midnight_podcast** — Load the 🌙 Midnight Podcast playlist with its own jingle\n"
            "**!thairmx** — Load the 🎵 Thai Remix playlist with its own jingle"
        ),
        inline=False
    )

    # ── Playback controls ────────────────────────────────────────────
    embed.add_field(
        name="⏯️ Playback Controls",
        value=(
            "**!skip [count]** — Skip current song (or multiple songs)\n"
            "**!repeat** — Toggle repeat for the current song\n"
            "**!repeat_playlist** — Toggle repeat for the last loaded playlist\n"
            "**!stop** — Clear queue, stop playback, and disconnect\n"
            "**!test_jingle** — Play the configured jingle in your voice channel"
        ),
        inline=False
    )

    # ── Queue info ───────────────────────────────────────────────────
    embed.add_field(
        name="📋 Queue",
        value="**!queue** — Show current track and next 10 songs in queue",
        inline=False
    )

    # ── Image / Fun ──────────────────────────────────────────────────
    embed.add_field(
        name="🎨 Images",
        value=(
            "**!wuwa** — Browse Wuthering Waves character art (SFW/NSFW picker)\n"
            "**!zani** — Get a random Zani image from Danbooru\n"
            "**!zanisafe** — Get a random Zani image from Safebooru"
        ),
        inline=False
    )

    
    embed.set_footer(text="Use !help to see this message again")
    if file:
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


# ---------------------------------------------------------------------------
# Wuthering Waves character → booru tag mapping
# Danbooru format: firstname_(wuthering_waves)
# ---------------------------------------------------------------------------
WUWA_CHARACTERS = {
    "Aalto":        "aalto_(wuthering_waves)",
    "Aemeath":      "aemeath_(wuthering_waves)",
    "Baizhi":       "baizhi_(wuthering_waves)",
    "Brant":        "brant_(wuthering_waves)",
    "Calcharo":     "calcharo_(wuthering_waves)",
    "Camellya":     "camellya_(wuthering_waves)",
    "Carlotta":     "carlotta_(wuthering_waves)",
    "Changli":      "changli_(wuthering_waves)",
    "Chixia":       "chixia_(wuthering_waves)",
    "Ciaccona":     "ciaccona_(wuthering_waves)",
    "Danjin":       "danjin_(wuthering_waves)",
    "Encore":       "encore_(wuthering_waves)",
    "Geshuido":     "geshuido_(wuthering_waves)",
    "Jianxin":      "jianxin_(wuthering_waves)",
    "Jiyan":        "jiyan_(wuthering_waves)",
    "Lumi":         "lumi_(wuthering_waves)",
    "Luoying":      "luoying_(wuthering_waves)",
    "Luuk Herssen": "luuk_herssen_(wuthering_waves)",
    "Mortefi":      "mortefi_(wuthering_waves)",
    "Phoebe":       "phoebe_(wuthering_waves)",
    "Phrolova":     "phrolova_(wuthering_waves)",
    "Roccia":       "roccia_(wuthering_waves)",
    "Rover (F)":    "rover_(wuthering_waves)",
    "Rover (M)":    "rover_(wuthering_waves)",
    "Sanhua":       "sanhua_(wuthering_waves)",
    "Shorekeeper":  "shorekeeper_(wuthering_waves)",
    "Taoqi":        "taoqi_(wuthering_waves)",
    "The Shorekeeper": "shorekeeper_(wuthering_waves)",
    "Verina":       "verina_(wuthering_waves)",
    "Xiangli Yao":  "xiangli_yao_(wuthering_waves)",
    "Yangyang":     "yangyang_(wuthering_waves)",
    "Yinlin":       "yinlin_(wuthering_waves)",
    "Youhu":        "youhu_(wuthering_waves)",
    "Yuanwu":       "yuanwu_(wuthering_waves)",
    "Zani":         "zani_(wuthering_waves)",
    "Zhezhi":       "zhezhi_(wuthering_waves)",
}

async def fetch_booru_image(tag: str, nsfw: bool, danbooru_user: str, danbooru_key: str):
    """Shared fetch logic for Danbooru (nsfw) or Safebooru (sfw).
    Returns (image_url, post_url, source_name) or raises on error."""
    if nsfw:
        url = "https://danbooru.donmai.us/posts.json"
        # Always mix in the requested tag, but forcefully ask for explicit things
        nsfw_tag = f"{tag} rating:explicit nipples"
        params = {'tags': nsfw_tag, 'limit': 100, 'login': danbooru_user, 'api_key': danbooru_key}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Fallback to questionable if explicit returns empty
        if not data:
            nsfw_tag = f"{tag} rating:questionable"
            params['tags'] = nsfw_tag
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
        if not data:
            return None, None, "Danbooru"
            
        post = random.choice(data)
        img = post.get('file_url', '')
        if not img.startswith('http'):
            img = f"https://danbooru.donmai.us{img}"
        return img, f"https://danbooru.donmai.us/posts/{post.get('id')}", "Danbooru"
    else:
        url = "https://danbooru.donmai.us/posts.json"
        
        sfw_tag = f"{tag} rating:general"
        params = {'tags': sfw_tag, 'limit': 100}
        
        if danbooru_user and danbooru_key:
            params['login'] = danbooru_user
            params['api_key'] = danbooru_key
            
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Fallback to sensitive if general returns empty
        if not data:
            sfw_tag = f"{tag} rating:sensitive"
            params['tags'] = sfw_tag
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
        if not data:
            return None, None, "Danbooru (Safe Mode)"
        post = random.choice(data)
        img = post.get('file_url', '')
        if not img.startswith('http'):
            img = f"https://danbooru.donmai.us{img}"
        return img, f"https://danbooru.donmai.us/posts/{post.get('id')}", "Danbooru (Safe Mode)"


class WuwaRatingView(discord.ui.View):
    """Second step: SFW or NSFW choice after character is selected."""
    def __init__(self, char_name: str, tag: str, danbooru_user: str, danbooru_key: str):
        super().__init__(timeout=60)
        self.char_name = char_name
        self.tag = tag
        self.danbooru_user = danbooru_user
        self.danbooru_key = danbooru_key

    async def _send_image(self, interaction: discord.Interaction, nsfw: bool):
        await interaction.response.defer(thinking=True)
        try:
            loop = asyncio.get_event_loop()
            img_url, post_url, source = await loop.run_in_executor(
                None,
                lambda: _fetch_booru_sync(self.tag, nsfw, self.danbooru_user, self.danbooru_key)
            )
        except Exception as e:
            await interaction.followup.send(embed=discord.Embed(
                title="❌ Fetch Error", description=str(e), color=discord.Color.red()
            ), ephemeral=True)
            return

        if not img_url:
            await interaction.followup.send(embed=discord.Embed(
                title="❌ No Results",
                description=f"No images found for **{self.char_name}** on {source}.",
                color=discord.Color.orange()
            ), ephemeral=True)
            return

        mode_label = "🔞 NSFW" if nsfw else "✅ SFW"
        embed = discord.Embed(
            title=f"🎨 {self.char_name} (Wuthering Waves) — {mode_label}",
            description=f"[View on {source}]({post_url})",
            color=discord.Color.red() if nsfw else discord.Color.teal()
        )
        embed.set_image(url=img_url)
        embed.set_footer(text=f"Source: {source} | Tag: {self.tag}")
        await interaction.followup.send(embed=embed)
        self.stop()

    @discord.ui.button(label="✅ SFW (Safebooru)", style=discord.ButtonStyle.green)
    async def sfw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_image(interaction, nsfw=False)

    @discord.ui.button(label="🔞 NSFW (Danbooru)", style=discord.ButtonStyle.red)
    async def nsfw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_image(interaction, nsfw=True)


def _fetch_booru_sync(tag: str, nsfw: bool, danbooru_user: str, danbooru_key: str):
    """Synchronous version of booru fetch for executor use."""
    if nsfw:
        url = "https://danbooru.donmai.us/posts.json"
        base_params = {'limit': 50}
        if danbooru_user and danbooru_key:
            base_params['login'] = danbooru_user
            base_params['api_key'] = danbooru_key

        # Fetch explicit properly and fall back to questionable
        combined = []
        for specific_tag in (f'{tag} rating:explicit nipples', f'{tag} rating:explicit', f'{tag} rating:questionable'):
            params = {**base_params, 'tags': specific_tag}
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                res = r.json()
                if res:
                    combined.extend(res)
                    break # if we got good explicit, no need to fallback
            except Exception:
                pass

        if not combined:
            return None, None, "Danbooru"
        post = random.choice(combined)
        img = post.get('file_url', '')
        if not img.startswith('http'):
            img = f"https://danbooru.donmai.us{img}"
        return img, f"https://danbooru.donmai.us/posts/{post.get('id')}", "Danbooru"
    else:
        url = "https://danbooru.donmai.us/posts.json"
        base_params = {'limit': 50}
        if danbooru_user and danbooru_key:
            base_params['login'] = danbooru_user
            base_params['api_key'] = danbooru_key
            
        combined = []
        for rating in ('general', 'sensitive'):
            params = {**base_params, 'tags': f'{tag} rating:{rating}'}
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                res = r.json()
                if res:
                    combined.extend(res)
                    break # if we got good results, we don't need to try next
            except Exception:
                pass
                
        if not combined:
            return None, None, "Danbooru (Safe Mode)"
        post = random.choice(combined)
        img = post.get('file_url', '')
        if not img.startswith('http'):
            img = f"https://danbooru.donmai.us{img}"
        return img, f"https://danbooru.donmai.us/posts/{post.get('id')}", "Danbooru (Safe Mode)"


class WuwaCharacterSelect(discord.ui.Select):
    """Dropdown to select a Wuthering Waves character."""
    def __init__(self, characters: list[tuple[str, str]], page: int, total_pages: int,
                 danbooru_user: str, danbooru_key: str):
        self.danbooru_user = danbooru_user
        self.danbooru_key = danbooru_key
        options = [
            discord.SelectOption(label=name, value=tag, description=tag)
            for name, tag in characters
        ]
        super().__init__(
            placeholder=f"Choose a character (Page {page}/{total_pages})…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        tag = self.values[0]
        # Find the character name from the tag
        char_name = next((n for n, t in WUWA_CHARACTERS.items() if t == tag), tag)
        view = WuwaRatingView(char_name, tag, self.danbooru_user, self.danbooru_key)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🎮 Wuthering Waves — {char_name}",
                description="Pick your source:",
                color=discord.Color.blurple()
            ),
            view=view
        )


class WuwaCharacterView(discord.ui.View):
    """Paginated character selection view."""
    PAGE_SIZE = 25

    def __init__(self, danbooru_user: str, danbooru_key: str, page: int = 1):
        super().__init__(timeout=60)
        self.danbooru_user = danbooru_user
        self.danbooru_key = danbooru_key
        self.page = page

        all_chars = sorted(WUWA_CHARACTERS.items())  # list of (name, tag)
        # Deduplicate by tag to avoid duplicate options
        seen_tags = set()
        unique_chars = []
        for name, tag in all_chars:
            if tag not in seen_tags:
                seen_tags.add(tag)
                unique_chars.append((name, tag))

        self.all_chars = unique_chars
        total_pages = max(1, (len(unique_chars) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.total_pages = total_pages

        start = (page - 1) * self.PAGE_SIZE
        page_chars = unique_chars[start:start + self.PAGE_SIZE]

        self.add_item(WuwaCharacterSelect(page_chars, page, total_pages, danbooru_user, danbooru_key))

        if page > 1:
            self.add_item(WuwaPrevButton(danbooru_user, danbooru_key, page))
        if page < total_pages:
            self.add_item(WuwaNextButton(danbooru_user, danbooru_key, page))


class WuwaNextButton(discord.ui.Button):
    def __init__(self, danbooru_user, danbooru_key, current_page):
        super().__init__(label="Next ▶", style=discord.ButtonStyle.blurple)
        self.danbooru_user = danbooru_user
        self.danbooru_key = danbooru_key
        self.current_page = current_page

    async def callback(self, interaction: discord.Interaction):
        new_view = WuwaCharacterView(self.danbooru_user, self.danbooru_key, self.current_page + 1)
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎮 Wuthering Waves", description="Pick a character:", color=discord.Color.blurple()),
            view=new_view
        )


class WuwaPrevButton(discord.ui.Button):
    def __init__(self, danbooru_user, danbooru_key, current_page):
        super().__init__(label="◀ Prev", style=discord.ButtonStyle.blurple)
        self.danbooru_user = danbooru_user
        self.danbooru_key = danbooru_key
        self.current_page = current_page

    async def callback(self, interaction: discord.Interaction):
        new_view = WuwaCharacterView(self.danbooru_user, self.danbooru_key, self.current_page - 1)
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎮 Wuthering Waves", description="Pick a character:", color=discord.Color.blurple()),
            view=new_view
        )


@bot.command(name='wuwa', help='Browse Wuthering Waves character art from Danbooru or Safebooru')
async def wuwa(ctx):
    """Interactive character picker for Wuthering Waves art"""
    view = WuwaCharacterView(DANBOORU_USERNAME, DANBOORU_API_KEY)
    embed = discord.Embed(
        title="🎮 Wuthering Waves",
        description=f"Pick a character to browse art for ({len(set(WUWA_CHARACTERS.values()))} resonators available):",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed, view=view)


@bot.command(name='zani', help='Get a random Zani (Wuthering Waves) image from Danbooru')
async def zani(ctx):
    """Fetch a random image of Zani from Danbooru"""
    try:
        print(f"\n[*] !zani command triggered by {ctx.author}")
        
        url = "https://danbooru.donmai.us/posts.json"
        params = {
            'tags': 'zani_(wuthering_waves)',
            'limit': 100,  # Fetch more images for better randomization
        }
        
        print("[*] Attempting to fetch from Danbooru...")
        headers = {}
        if DANBOORU_USERNAME and DANBOORU_API_KEY:
            print(f"[*] Using Danbooru authentication: {DANBOORU_USERNAME}")
            # Danbooru API uses HTTP Basic Auth or passing login/api_key in query string. 
            # We can use requests auth parameter or params.
            params['login'] = DANBOORU_USERNAME
            params['api_key'] = DANBOORU_API_KEY
        else:
            print("[*] No Danbooru authentication configured, using unauthenticated request")
        
        print(f"[*] Danbooru URL: {url}")
        # Note: Do not print params if it contains the API key to avoid leaking it in logs
        print(f"[*] Danbooru params prepared")
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"[+] Successfully fetched {len(data)} images from Danbooru")
        source = "Danbooru"
        source_url = "https://danbooru.donmai.us"
        
        if not data or len(data) == 0:
            print("[!] No images found!")
            embed = discord.Embed(
                title="❌ No Results",
                description="Could not find any images with that tag.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Pick a random post from the results
        post = random.choice(data)
        image_url = post.get('file_url')
        post_id = post.get('id')
        print(f"[+] Selected random image: ID {post_id}")
        
        if not image_url:
            print(f"[!] No file_url in post {post_id}")
            embed = discord.Embed(
                title="❌ Error",
                description="Could not extract image URL from post.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Ensure image_url is absolute
        if not image_url.startswith('http'):
            image_url = f"https://{source_url.lstrip('https://')}/{image_url}"
        
        print(f"[+] Image URL: {image_url}")
        
        # Create embed with image
        embed = discord.Embed(
            title="🎨 Zani (Wuthering Waves)",
            description=f"[View on {source}]({source_url}/posts/{post_id})",
            color=discord.Color.purple()
        )
        embed.set_image(url=image_url)
        
        # Add metadata if available
        if post.get('tag_string'):
            # Danbooru uses 'tag_string' instead of 'tags'
            embed.add_field(name="Tags", value=post.get('tag_string')[:100] + "...", inline=False)
        elif post.get('tags'):
            embed.add_field(name="Tags", value=post.get('tags')[:100] + "...", inline=False)
            
        if post.get('score'):
            embed.add_field(name="Score", value=str(post.get('score')), inline=True)
        
        embed.set_footer(text=f"Source: {source}")
        
        print(f"[+] Sending embed to Discord")
        await ctx.send(embed=embed)
        
    except requests.exceptions.Timeout:
        print(f"[!] Danbooru request timed out")
        embed = discord.Embed(
            title="❌ Timeout",
            description="Danbooru request timed out. Try again later.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except requests.exceptions.RequestException as e:
        print(f"[!] Danbooru network error: {type(e).__name__}: {e}")
        embed = discord.Embed(
            title="❌ Network Error",
            description=f"Cannot reach Danbooru. ({type(e).__name__})",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"[!] Error in !zani command: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='zanisafe', help='Get a random Zani (Wuthering Waves) image from Safebooru')
async def zanisafe(ctx):
    """Fetch a random image of Zani from Safebooru"""
    try:
        print(f"\n[*] !zanisafe command triggered by {ctx.author}")
        
        url = "https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1"
        params = {
            'tags': 'zani_(wuthering_waves)',
            'limit': 100,  # Fetch more images for better randomization
        }
        
        print(f"[*] Attempting to fetch from Safebooru...")
        print(f"[*] Safebooru URL: {url}")
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"[+] Successfully fetched {len(data)} images from Safebooru")
        source = "Safebooru"
        source_url = "https://safebooru.org"
        
        if not data or len(data) == 0:
            print("[!] No images found!")
            embed = discord.Embed(
                title="❌ No Results",
                description="Could not find any images with that tag.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Pick a random post from the results
        post = random.choice(data)
        
        # Safebooru image format: //safebooru.org/images/directory/image.ext
        # Or file_url string mapping directly
        image_url = post.get('file_url')
        if not image_url and post.get('directory') and post.get('image'):
            image_url = f"https://safebooru.org/images/{post.get('directory')}/{post.get('image')}"

        post_id = post.get('id')
        print(f"[+] Selected random image: ID {post_id}")
        
        if not image_url:
            print(f"[!] No valid image url in post {post_id}")
            embed = discord.Embed(
                title="❌ Error",
                description="Could not extract image URL from post.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Ensure image_url is fully qualified URL
        if not image_url.startswith('http'):
            image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://safebooru.org/{image_url.lstrip('/')}"
        
        print(f"[+] Image URL: {image_url}")
        
        # Create embed with image
        embed = discord.Embed(
            title="🎨 Zani (Wuthering Waves)",
            description=f"[View on {source}]({source_url}/index.php?page=post&s=view&id={post_id})",
            color=discord.Color.blue()
        )
        embed.set_image(url=image_url)
        
        # Add metadata if available
        if post.get('tags'):
            embed.add_field(name="Tags", value=post.get('tags')[:100] + "...", inline=False)
            
        if post.get('score'):
            embed.add_field(name="Score", value=str(post.get('score')), inline=True)
        
        embed.set_footer(text=f"Source: {source}")
        
        print(f"[+] Sending embed to Discord")
        await ctx.send(embed=embed)
        
    except requests.exceptions.Timeout:
        print(f"[!] Safebooru request timed out")
        embed = discord.Embed(
            title="❌ Timeout",
            description="Safebooru request timed out. Try again later.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except requests.exceptions.RequestException as e:
        print(f"[!] Safebooru network error: {type(e).__name__}: {e}")
        embed = discord.Embed(
            title="❌ Network Error",
            description=f"Cannot reach Safebooru. ({type(e).__name__})",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"[!] Error in !zanisafe command: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name='sourcecode', help='Send the bot.py source code file')
async def sourcecode(ctx):
    """Send the source code of bot.py"""
    print(f"\n[*] User {ctx.author} requested source code")
    try:
        await ctx.send("Here is the source code for bot.py:", file=discord.File(__file__))
    except Exception as e:
        print(f"[!] Error sending source code: {e}")
        await ctx.send(f"❌ Error sending source code: {str(e)}")

@bot.command(name='ui', help='Toggle the Music Player UI dashboard on or off. Usage: !ui on | !ui off')
async def toggle_ui(ctx, state: str):
    """Toggle the flashy Music Player dashboard"""
    guild_data = music_player.get_guild_data(ctx.guild.id)
    if state.lower() == 'on':
        guild_data['ui_enabled'] = True
        await ctx.send("✅ Music Player UI Dashboard has been **enabled**.")
    elif state.lower() == 'off':
        guild_data['ui_enabled'] = False
        await ctx.send("❌ Music Player UI Dashboard has been **disabled**. I will use simple text replies.")
        # Delete the last UI message if one exists to clean up
        last_msg = guild_data.get('last_ui_message')
        if last_msg:
            try:
                await last_msg.delete()
                guild_data['last_ui_message'] = None
            except:
                pass
    else:
        await ctx.send("⚠️ Usage: `!ui on` or `!ui off`")

# Bot Token - Set via environment variable DISCORD_BOT_TOKEN
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    print("[!] ERROR: DISCORD_BOT_TOKEN environment variable not set!")
    print("[*] Set it with: $env:DISCORD_BOT_TOKEN = 'your_token_here'")
    exit(1)

if __name__ == '__main__':
    try:
        print("[*] Starting Discord Music Bot...")
        print("[*] Commands: !load_playlist <URL>, !play, !skip, !queue, !test_jingle, !stop")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n[*] Bot shutting down...")
    except Exception as e:
        print(f"[!] Error starting bot: {e}")
