import sys

with open('d:/code/discord_radio2/bot.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Patch on_song_finished
old_finished = """        guild_data['jingle_count'] += 1

        print(f"[+] Song finished: {song_info.get('title', 'Unknown')}")
        print(f"[+] Songs played: {guild_data['jingle_count']}")

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
        if guild_data['jingle_count'] >= 2:"""

new_finished = """        if not song_info.get('skip_jingle'):
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
        if guild_data['jingle_count'] >= 2 and not song_info.get('skip_jingle'):"""

if old_finished in code:
    code = code.replace(old_finished, new_finished)
    print('Patched on_song_finished success.')
else:
    print('Failed to patch on_song_finished')
    sys.exit(1)

# 2. Patch play_queue -> _play_core
old_def = """@bot.command(name='play', help='Play the queued songs or a single URL/song. Usage: !play [<URL/song name>]')
async def play_queue(ctx, *, url: str = None):
    \"\"\"Start playing the queue or play a specific song by URL or search query\"\"\""""

new_def = """@bot.command(name='play', help='Play the queued songs or a single URL/song. Usage: !play [<URL/song name>]')
async def play_queue(ctx, *, url: str = None):
    \"\"\"Start playing the queue or play a specific song by URL or search query\"\"\"
    await _play_core(ctx, url=url, skip_jingle=False)

@bot.command(name='live_play', help='Play a song without jingle interruption. Usage: !live_play [<URL/song name>]')
async def live_play_queue(ctx, *, url: str = None):
    \"\"\"Play a specific song without jingle interruption\"\"\"
    await _play_core(ctx, url=url, skip_jingle=True)

async def _play_core(ctx, url: str = None, skip_jingle: bool = False):
    \"\"\"Core playback logic for play and live_play commands\"\"\""""

if old_def in code:
    code = code.replace(old_def, new_def)
    print('Patched play_queue def success.')
else:
    print('Failed to patch play_queue def')
    sys.exit(1)

# 3. Patch song dict creation
old_song_dict = """                # Create song dict with search result metadata
                song = {
                    'url': song_url,
                    'title': first_result.get('title', 'Unknown Title'),
                    'duration': first_result.get('duration', 0),
                    'uploader': first_result.get('uploader', 'Unknown Artist')
                }"""

new_song_dict = """                # Create song dict with search result metadata
                song = {
                    'url': song_url,
                    'title': first_result.get('title', 'Unknown Title'),
                    'duration': first_result.get('duration', 0),
                    'uploader': first_result.get('uploader', 'Unknown Artist'),
                    'skip_jingle': skip_jingle
                }"""

if old_song_dict in code:
    code = code.replace(old_song_dict, new_song_dict)
    print('Patched song dict success.')
else:
    print('Failed to patch song dict')
    sys.exit(1)

# 4. Patch playlist track mapping
old_playlist = """        else:
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
            song = songs[0]"""

new_playlist = """        else:
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
            if skip_jingle:
                song['skip_jingle'] = True"""

if old_playlist in code:
    code = code.replace(old_playlist, new_playlist)
    print('Patched playlist track mapping success.')
else:
    print('Failed to patch playlist track mapping')
    sys.exit(1)

# 5. Patch empty queue run all live
old_start_queue = """    # Start playing queue
    guild_data['jingle_count'] = 0"""

new_start_queue = """    if not url and skip_jingle:
        for s in guild_data['queue']:
            if isinstance(s, dict):
                s['skip_jingle'] = True

    # Start playing queue
    guild_data['jingle_count'] = 0"""

if old_start_queue in code:
    code = code.replace(old_start_queue, new_start_queue)
    print('Patched queue start live success.')
else:
    print('Failed to patch queue start live')
    sys.exit(1)

with open('d:/code/discord_radio2/bot.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('All patches applied!')
