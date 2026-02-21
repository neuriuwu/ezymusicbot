import yt_dlp

ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True, 
    'skip_download': True
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    result = ydl.extract_info("ytsearch1:Never Gonna Give You Up Rick Astley", download=False)
    print("Is list of dicts with entries?", isinstance(result, dict) and 'entries' in result)
    if 'entries' in result:
        print("First entry:", result['entries'][0])
