html = open('playlist.html', encoding='utf-8').read()
import re

# Try to find where "Shape of You" or another known track from Today's Top hits might be
import json

# Let's find all script tags and look for JSON objects with "name" and "artists"
scripts = re.findall(r'<script.*?>(.*?)</script>', html, re.DOTALL)
for s in scripts:
    if '"artists"' in s and '"name"' in s:
        # maybe it's valid json?
        if s.strip().startswith('{') or s.strip().startswith('['):
            try:
                data = json.loads(s)
                print("Found JSON script!", len(s))
            except:
                print("Invalid JSON, but looks promising", len(s))

# Spotify's new web arch puts track data in a redux store script:
# <script id="initial-state" type="application/json">...
# Oh wait, we already checked for id="initial-state" above with an exact match
# Let's do a loose match
match = re.search(r'<script.*?(initial-state|__preload).*?>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
if match:
    print("Found", match.group(1))

