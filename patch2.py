import sys

with open('d:/code/discord_radio2/bot.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add preload_task to get_guild_data
old_guild_data = """            # Flag to prevent automatic queue play after interrupt
            'interrupt_next': False,
        }
    return self.current_guild_data[guild_id]"""
new_guild_data = """            # Flag to prevent automatic queue play after interrupt
            'interrupt_next': False,
            'preload_task': None,
        }
    return self.current_guild_data[guild_id]"""

if old_guild_data in code:
    code = code.replace(old_guild_data, new_guild_data)
    print("Patched get_guild_data")
else:
    print("Failed to patch get_guild_data")

# 2. Add preload_next_song method to MusicPlayer
# We can just insert it before play_audio
old_play_audio_def = """    async def play_audio(self, guild_id, voice_client, audio_url, song_info):"""
new_preload_method = """    async def preload_next_song(self, guild_id):
        \"\"\"Background task to preload the next song's audio URL 10s before current song ends\"\"\"
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

    async def play_audio(self, guild_id, voice_client, audio_url, song_info):"""

if old_play_audio_def in code:
    code = code.replace(old_play_audio_def, new_preload_method)
    print("Patched play_audio definition to include preload_next_song")
else:
    print("Failed to patch play_audio definition")

# 3. Modify play_audio to cancel existing and start new preload task
old_play_audio_body = """        guild_data['current_voice_client'] = voice_client
        
        print(f"[*] Now playing: {song_info['title']} by {song_info['uploader']}")
        
        # Use direct audio source"""

new_play_audio_body = """        guild_data['current_voice_client'] = voice_client
        
        # Cancel any existing preload task
        if guild_data.get('preload_task'):
            guild_data['preload_task'].cancel()
            guild_data['preload_task'] = None
            
        print(f"[*] Now playing: {song_info['title']} by {song_info['uploader']}")
        
        # Start a new preload task if we have a valid duration > 10s
        duration = song_info.get('duration', 0)
        if duration > 10:
            loop = self.bot.loop
            guild_data['preload_task'] = loop.create_task(self.preload_next_song(guild_id))
        
        # Use direct audio source"""

if old_play_audio_body in code:
    code = code.replace(old_play_audio_body, new_play_audio_body)
    print("Patched play_audio body")
else:
    print("Failed to patch play_audio body")

# 4. Modify play_next_song to use preloaded URL
old_play_next_song = """        song = guild_data['queue'].popleft()
        print(f"[*] Getting audio URL for: {song['title']}")
        
        audio_url = await self.get_audio_url(song['url'])
        if audio_url:
            await self.play_audio(guild_id, voice_client, audio_url, song)"""

new_play_next_song = """        song = guild_data['queue'].popleft()
        
        audio_url = song.get('preloaded_url')
        if not audio_url:
            print(f"[*] Getting audio URL for: {song['title']}")
            audio_url = await self.get_audio_url(song['url'])
        else:
            print(f"[*] Using preloaded audio URL for: {song['title']}")
            
        if audio_url:
            await self.play_audio(guild_id, voice_client, audio_url, song)"""

if old_play_next_song in code:
    code = code.replace(old_play_next_song, new_play_next_song)
    print("Patched play_next_song")
else:
    print("Failed to patch play_next_song")

# 5. Cancel preload task in 'stop'
old_stop = """    if voice_client and voice_client.is_connected():
        guild_data['playing'] = False
        guild_data['queue'].clear()
        voice_client.stop()"""

new_stop = """    if voice_client and voice_client.is_connected():
        guild_data['playing'] = False
        guild_data['queue'].clear()
        if guild_data.get('preload_task'):
            guild_data['preload_task'].cancel()
            guild_data['preload_task'] = None
        voice_client.stop()"""

if old_stop in code:
    code = code.replace(old_stop, new_stop)
    print("Patched stop")
else:
    print("Failed to patch stop")

with open('d:/code/discord_radio2/bot.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("All done!")
