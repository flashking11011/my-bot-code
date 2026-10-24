import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import datetime
import aiohttp
from bs4 import BeautifulSoup
import re
import urllib.parse

# --- CONFIGURATION ---
TOKEN = 'YOUR_BOT_TOKEN_HERE'

class BloxGrandmasterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Runtime Live Data Caches
        self.live_market_cache = {}
        self.stock_subscribers = {} 
        self.current_stock = []
        self.codes_channel_id = None
        
        # Tracked codes cache to prevent duplication loops
        self.posted_codes = set()
        self.initial_seed_done = False

    async def setup_hook(self):
        self.live_scraper_loop.start()
        self.merchant_stock_loop.start()
        self.code_tracker_loop.start()
        await self.tree.sync()

bot = BloxGrandmasterBot()

# --- LIVE WIKI SCRAPER: CODE RETRIEVAL MODULE ---
async def scrape_blox_fruits_codes():
    """
    Downloads and parses the Working Codes table directly from the official Fandom Wiki page.
    """
    url = "https://blox-fruits.fandom.com/wiki/Codes"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    scraped_codes = {}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=12) as response:
                if response.status != 200: return scraped_codes
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the header element containing "Working Codes"
        working_headline = soup.find(id="Working_Codes") or soup.find(lambda tag: tag.name in ['h3', 'h2'] and 'Working Codes' in tag.text)
        if not working_headline:
            return scraped_codes
            
        # Locate the next sequential table node structure following the header
        table = working_headline.find_next('table')
        if not table:
            return scraped_codes
            
        rows = table.find_all('tr')
        for row in rows[1:]: # Skip header structural row block element
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 2:
                # Extract clean string tokens by removing noise text segments
                code_text = cols[0].get_text(strip=True).replace('[-]', '').strip()
                reward_text = cols[1].get_text(strip=True)
                
                # Protect against parsing dead space nodes or layout wrappers
                if code_text and len(code_text) > 2 and not code_text.lower().startswith('code'):
                    scraped_codes[code_text] = reward_text
                    
        return scraped_codes
    except Exception as e:
        print(f"[!] Codes Scraper Error: {str(e)}")
        return scraped_codes

# --- LIVE WEB SCRAPER: VALUATION PLATFORM ---
async def scrape_bloxfruits_values():
    url = "https://bloxfruitsvalues.com"
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" }
    extracted_data = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=12) as response:
                if response.status != 200: return None
                html = await response.text()
        soup = BeautifulSoup(html, 'html.parser')
        for h3 in soup.find_all('h3'):
            name = h3.get_text(strip=True)
            if not name: continue
            parent_text = h3.parent.get_text(" ", strip=True) if h3.parent else ""
            val_match = re.search(r'([\d\.]+[B|M|K])', parent_text)
            dem_match = re.search(r'Demand\s*(\d+/\d+)', parent_text)
            trend_match = re.search(r'(Stable|Overpaid|Unstable|Hyped|Underpaid)', parent_text)
            beli_match = re.search(r'Beli\s*Price\s*([\d\.]+[M|K]?)', parent_text)
            extracted_data[name.title()] = {
                "value": val_match.group(1) if val_match else "Unknown",
                "demand": dem_match.group(1) if dem_match else "N/A",
                "trend": trend_match.group(1) if trend_match else "Stable",
                "beli": beli_match.group(1) if beli_match else "N/A"
            }
        return extracted_data
    except Exception: return None

# --- LIVE WEB SCRAPER: FANDOM WIKI INTELLIGENCE ENGINE ---
async def fetch_fandom_wiki_data(query: str):
    clean_query = query.strip()
    encoded_query = urllib.parse.quote_plus(clean_query)
    search_url = f"https://fandom.com{encoded_query}&format=json"
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers=headers, timeout=10) as resp:
                if resp.status != 200: return None
                search_data = await resp.json()
            results = search_data.get("query", {}).get("search", [])
            if not results: return None
            best_match_title = results[0]["title"]
            formatted_title = best_match_title.replace(" ", "_")
            article_url = f"https://blox-fruits.fandom.com/wiki/{formatted_title}"
            async with session.get(article_url, headers=headers, timeout=10) as art_resp:
                if art_resp.status != 200: return None
                html_content = await art_resp.text()
            soup = BeautifulSoup(html_content, 'html.parser')
            content_div = soup.find(id="mw-content-text") or soup.find(class_="mw-parser-output")
            if not content_div: return None
            paragraphs = []
            for element in content_div.find_all(['p', 'h2', 'h3']):
                if element.name.startswith('h'):
                    h_text = element.get_text(strip=True).replace("[edit]", "")
                    if h_text and len(paragraphs) < 5: paragraphs.append(f"\n**{h_text}**")
                else:
                    p_text = re.sub(r'\[\d+\]', '', element.get_text(strip=True))
                    if p_text and len(p_text) > 20 and len(paragraphs) < 5: paragraphs.append(p_text)
            if paragraphs:
                return { "title": best_match_title, "url": article_url, "text": "\n".join(paragraphs[:4])[:1800] }
    except Exception: return None

def parse_live_value_to_int(val_str):
    try:
        val_str = val_str.upper().strip()
        if 'B' in val_str: return int(float(val_str.replace('B', '')) * 1_000_000_000)
        if 'M' in val_str: return int(float(val_str.replace('M', '')) * 1_000_000)
        if 'K' in val_str: return int(float(val_str.replace('K', '')) * 1_000)
        return int(float(val_str))
    except ValueError: return 0

# --- BACKGROUND AUTOMATED CACHE REFRESH LOOPS ---
@tasks.loop(minutes=30)
async def live_scraper_loop():
    await bot.wait_until_ready()
    fresh_data = await scrape_bloxfruits_values()
    if fresh_data: bot.live_market_cache = fresh_data

@tasks.loop(minutes=30)
async def code_tracker_loop():
    """
    Background worker loop that scans the Fandom wiki, verifies index items,
    and deploys alerts for freshly parsed promo codes.
    """
    await bot.wait_until_ready()
    
    # Query live Fandom data terminal matrix
    live_wiki_codes = await scrape_blox_fruits_codes()
    if not live_wiki_codes:
        return

    # Seed existing database keys on initial runtime connection to stop historic item notifications
    if not bot.initial_seed_done:
        for code in live_wiki_codes.keys():
            bot.posted_codes.add(code)
        bot.initial_seed_done = True
        print(f"[✓] Code Engine Synced! Seaded {len(bot.posted_codes)} active promo codes into tracker memory.")
        return

    # Isolate missing element items to determine new discoveries
    new_codes = {c: r for c, r in live_wiki_codes.items() if c not in bot.posted_codes}
    
    if new_codes and bot.codes_channel_id:
        channel = bot.get_channel(bot.codes_channel_id)
        if not channel: return
        
        embed = discord.Embed(
            title="🎁 NEW BLOX FRUITS REDEEM CODES SCALED", 
            color=discord.Color.magenta(),
            url="https://blox-fruits.fandom.com/wiki/Codes#Working_Codes",
            timestamp=datetime.datetime.utcnow()
        )
        for code, reward in new_codes.items():
            embed.add_field(name=f"🔑 Active Code: `{code}`", value=f"🎁 Verification Benefit: **{reward}**", inline=False)
            bot.posted_codes.add(code) # Commit to localized storage arrays
            
        embed.set_footer(text="Parsed Live from blox-fruits.fandom.com")
        await channel.send(content="@everyone 🚀 New official promo code drop detected on the Fandom Wiki! Redeem it immediately!", embed=embed)

@tasks.loop(hours=4)
async def merchant_stock_loop():
    await bot.wait_until_ready()
    pool = list(bot.live_market_cache.keys()) if bot.live_market_cache else ["Kitsune", "Dough", "Buddha", "Portal"]
    stock = ["Rocket", "Spin"] + random.sample([f for f in pool if f not in ["Rocket", "Spin"]], min(4, len(pool)))
    bot.current_stock = stock
    
    pings = []
    for fruit in stock:
        if fruit in bot.stock_subscribers:
            pings.extend([f"<@{uid}>" for uid in bot.stock_subscribers[fruit]])
    ping_str = f" 🔥 Pings: {' '.join(set(pings))}" if pings else ""
    
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name="blox-stock") or guild.text_channels
        try:
