# Setting Up Custom Jingles

The Discord Music Bot supports three ways to play jingles:

## Option 1: Use Windows Built-in Sound (Easiest)
The bot automatically uses `C:/Windows/Media/tada.wav` if it exists. No configuration needed!

## Option 2: Use a Custom Audio File

### Step 1: Prepare Your Audio File
- Convert your jingle to MP3, WAV, OGG, or another FFmpeg-supported format
- Recommended: WAV or MP3 (2-3 seconds long)
- Example tools:
  - **Audacity** (free): https://www.audacityteam.org/
  - **FFmpeg** (command line): `ffmpeg -i input.mp3 -q:a 9 -n output.wav`

### Step 2: Place the File in Your Bot Directory
```
discord_radio/
  ├── bot.py
  ├── requirements.txt
  └── jingle.mp3  ← Put your file here
```

### Step 3: Configure bot.py
Open `bot.py` and find this section (around line 45):
```python
class MusicPlayer:
    def __init__(self, bot):
        # ...
        self.jingle_path = None  # Set to "path/to/your/jingle.mp3" to use a custom file
```

Change it to:
```python
self.jingle_path = "jingle.mp3"  # Or your file path
```

Or use an absolute path:
```python
self.jingle_path = "D:/code/discord_radio/my_jingle.mp3"
```

## Option 3: Use System Sounds

### Windows System Sounds
```python
self.jingle_path = "C:/Windows/Media/tada.wav"           # Tada sound
self.jingle_path = "C:/Windows/Media/Alarm01.wav"        # Alarm
self.jingle_path = "C:/Windows/Media/Chime.wav"          # Chime
self.jingle_path = "C:/Windows/Media/Ding.wav"           # Ding
self.jingle_path = "C:/Windows/Media/notify.wav"         # Notify
```

### macOS System Sounds
```python
self.jingle_path = "/System/Library/Sounds/Glass.aiff"
self.jingle_path = "/System/Library/Sounds/Pop.aiff"
self.jingle_path = "/System/Library/Sounds/Bottle.aiff"
```

## Option 4: Let the Bot Generate a Beep (Default)
If no custom jingle is found, the bot automatically generates a simple sine wave beep. No configuration needed!

## How to Find Windows Sound Files

```powershell
# Open in PowerShell
explorer "C:\Windows\Media"
```

Or browse to: `C:\Windows\Media\`

Common files:
- `tada.wav` - Cheerful tada sound
- `chime.wav` - Chim chime sound
- `click.wav` - Click sound
- `ding.wav` - Ding sound
- `pop.wav` - Pop sound

## Testing Your Jingle Setup

1. Start the bot: `python bot.py`
2. Load a playlist: `!load_playlist <URL>`
3. Start playing: `!play`
4. Wait for 2 songs to complete - the jingle will play after the 2nd song

## Creating Your Own Jingle with FFmpeg

### Create a 3-second beep:
```bash
ffmpeg -f lavfi -i sine=frequency=1000:duration=3 -q:a 9 my_jingle.wav
```

### Create a 2-second double beep:
```bash
ffmpeg -f lavfi -i "sine=frequency=1000|sine=frequency=1500:duration=2" my_jingle.wav
```

### Convert MP3 to WAV:
```bash
ffmpeg -i song.mp3 -q:a 9 jingle.wav
```

## Troubleshooting

### "File not found" error
- Make sure the file path is correct
- Use forward slashes `/` or double backslashes `\\` in Python
- Test the path exists: `python -c "import os; print(os.path.exists('your/path'))"`

### Jingle doesn't play
- Check FFmpeg is installed: `ffmpeg -version`
- Check file is a valid audio format: `ffmpeg -i jingle.mp3`
- Check bot has permission to read the file

### Bad audio quality
- Ensure FFmpeg is installed properly
- Try converting to WAV: `ffmpeg -i jingle.mp3 -q:a 9 jingle.wav`
- Check audio format compatibility

## Best Practices

✅ **Do:**
- Use 2-3 second jingles
- Keep file size small (under 500KB)
- Use WAV or MP3 formats
- Test the jingle before deploying

❌ **Don't:**
- Use very long jingles (slows down playback)
- Use unsupported formats
- Use copyrighted music without permission
- Mix custom jingles with generated beeps

## Example: Complete Setup for Custom Jingle

1. **Download a sound**: Find a radio jingle online
2. **Convert format**: `ffmpeg -i jingle.mp3 -q:a 9 jingle.wav`
3. **Place file**: Copy to `D:/code/discord_radio/jingle.wav`
4. **Configure bot**: In `bot.py`, set `self.jingle_path = "jingle.wav"`
5. **Restart bot**: Run `python bot.py`
6. **Test**: Load a playlist and wait for the jingle after 2 songs!
