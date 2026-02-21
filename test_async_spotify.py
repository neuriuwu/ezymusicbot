import asyncio
import aiohttp
import re
import time

async def fetch_spotify_metadata(session, url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with session.get(url, headers=headers) as response:
            text = await response.text()
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

async def main():
    with open('playlist.html', encoding='utf-8') as f:
        html = f.read()
    
    track_urls = re.findall(r'<meta name="music:song" content="([^"]+)"', html)
    
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_spotify_metadata(session, url) for url in track_urls]
        results = await asyncio.gather(*tasks)
        print(f"Fetched {len(results)} tracks in {time.time() - start_time:.2f} seconds")
        for r in results[:5]:
            print(r)

if __name__ == '__main__':
    asyncio.run(main())
