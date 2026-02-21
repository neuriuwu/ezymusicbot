import yt_dlp

ydl_opts = {'skip_download': True}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info("ytsearch1:Never Gonna Give You Up", download=False)
    
    if 'entries' in info:
        print("Has entries! Length:", len(info['entries']))
        first = info['entries'][0]
        print("First entry has formats?", 'formats' in first)
        print("Top-level info has formats?", 'formats' in info)
