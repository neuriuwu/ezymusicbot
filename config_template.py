# Discord Music Bot Configuration Template
# Copy this to config.py and modify as needed

# Bot Prefix for commands
BOT_PREFIX = '!'

# Discord Bot Token (can also use DISCORD_BOT_TOKEN environment variable)
DISCORD_BOT_TOKEN = 'tokenhere'

# YT-DLP Audio Format
# Options: 'bestaudio/best', 'worst', '18' (360p video), etc.
AUDIO_FORMAT = 'bestaudio/best'

# FFmpeg Options
FFMPEG_BEFORE_OPTIONS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
FFMPEG_OPTIONS = '-vn'

# Music Playback Settings
SONGS_BEFORE_JINGLE = 2  # Number of songs before playing a jingle
JINGLE_AUDIO_FILE = 'whatever_the_fucks_this_is.wav'  # Path to your jingle audio file (relative or absolute)

# Logging
ENABLE_LOGGING = True
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR

# Timeout Settings (in seconds)
PLAYLIST_PARSE_TIMEOUT = 30
AUDIO_DOWNLOAD_TIMEOUT = 30

# Voice Channel Settings
AUTO_DISCONNECT_IDLE = True
IDLE_TIMEOUT_SECONDS = 300  # Disconnect after 5 minutes of no songs playing

# Queue Settings
MAX_SONGS_PER_PLAYLIST = None  # None for unlimited, or set a number like 100
DUPLICATE_SONGS_ALLOWED = True

# Logging Discord IDs (for admin notifications)
ADMIN_LOG_CHANNEL = None  # Set to a channel ID for admin logs
ERROR_LOG_CHANNEL = None   # Set to a channel ID for error logs

# Experimental Features
ENABLE_SONG_SEARCH = True  # Allow searching YouTube via !search command
ENABLE_SKIP_QUEUE = True   # Allow skipping to specific songs in queue

# Danbooru Configuration
# Get your API key from: https://danbooru.donmai.us/profile
DANBOORU_USERNAME = ''  # Your Danbooru username (leave empty to disable authentication)
DANBOORU_API_KEY = ''   # Your Danbooru API key (leave empty to disable authentication)
