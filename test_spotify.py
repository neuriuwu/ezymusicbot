import requests
import re

url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" # Today's Top Hits
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)

title_match = re.search(r'<meta property="og:title" content="([^"]+)"', response.text)
desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', response.text)

print("Title:", title_match.group(1) if title_match else None)
print("Desc:", desc_match.group(1) if desc_match else None)
