import os
import sys
import logging
import re
import json
import time
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple

# ----------------------------------------------------
# 🛠️ SYSTEM ENVIRONMENT PATH SETUP
# ----------------------------------------------------
_this_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_this_dir)
_libs_dir = os.path.join(_root_dir, "applet_python_libs")
for p in [_libs_dir, _root_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] BloxGrandmaster: %(message)s")
logger = logging.getLogger("BloxGrandmaster")

TOKEN = os.getenv("BLOX_FRUITS_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

# ----------------------------------------------------
# ⚙️ CONFIGURATION & DESIGNER OVERLAYS
# ----------------------------------------------------
XZVIER_CHANNEL_ID = 1540698357641519125  
DESIGNER_USER_ID = 1325001135366471690   

GLOBAL_AI_COOLDOWN = 10.0  
USER_COOLDOWN_TRACKER: Dict[int, float] = {}  

# ----------------------------------------------------
# 🌐 DEEP LIVE DATABASE PARSER ENGINE (Market Values)
# ----------------------------------------------------
async def fetch_all_market_values() -> Dict[str, Dict[str, Any]]:
    url = "https://bloxfruitsvalues.com"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    market_data = {}

    if not HAS_BS4: return market_data
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
                if response.status != 200: return market_data
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                for header in soup.find_all(['h3', 'h4', 'div', 'p', 'span']):
                    name_text = header.get_text(strip=True)
                    if not name_text or len(name_text) > 40: continue
                    
                    card = header.find_parent(class_=lambda x: x and any(k in x.lower() for k in ['card', 'item', 'value', 'row'])) or header.parent
                    if not card: continue
                    card_text = card.get_text(" ", strip=True)
                    
                    trade_val, perm_val, demand, trend = "Unknown", "N/A", "N/A", "Stable"
                    money_vals = re.findall(r'(\d+(?:\.\d+)?\s*[MBKmbk])', card_text)
                    if len(money_vals) >= 1: trade_val = money_vals.upper()
                    if len(money_vals) >= 2: perm_val = money_vals.upper()
                        
                    demand_match = re.search(r'(?:Demand|Popularity)[:\s]*(\d+/\d+|\d+)', card_text, re.IGNORECASE)
                    if demand_match: 
                        demand = demand_match.group(1) if "/" in demand_match.group(1) else f"{demand_match.group(1)}/10"
                    
                    for status in ["Stable", "Overpaid", "Unstable", "Underpaid", "Hyped"]:
                        if status.lower() in card_text.lower(): trend = status; break
                    
                    market_data[name_text.lower().strip()] = {
                        "name": name_text, "trade_val": trade_val, "perm_val": perm_val, 
                        "demand": demand, "trend": trend
                    }
    except Exception as e: logger.error(f"Global value scrape error: {e}")
    return market_data

async def fetch_fruit_detailed_value(search_query: str) -> Optional[Dict[str, str]]:
    matrix = await fetch_all_market_values()
    clean = search_query.lower().strip()
    for key, data in matrix.items():
        if clean == key:  
            return {
                "name": data["name"], "trade_val": data["trade_val"], "perm_val": data["perm_val"],
                "demand": data["demand"], "rarity": "Fruit/Item", "trend": data["trend"],
                "beli": "N/A", "robux": "N/A", "thumb": "https://bloxfruitsvalues.com",
                "best_used": "PvP, Raids, Grinding & Marketplace Packages"
            }
    return None

# ----------------------------------------------------
# 📖 DYNAMIC BLOX FRUITS FANDOM WIKI SCRAPER
# ----------------------------------------------------
async def search_blox_wiki_content(query: str) -> Tuple[str, str]:
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://fandom.com{encoded_query}"
    fallback_url = "https://fandom.com"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    if not HAS_BS4: return "BeautifulSoup4 missing.", fallback_url

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers=headers, timeout=6) as response:
                if response.status != 200: return "", fallback_url
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                result_link = (
                    soup.find('a', class_='unified-search__result__title') or 
                    soup.find('a', class_='result-link')
                )
                target_url = result_link['href'] if result_link and result_link.has_attr('href') else fallback_url

            if target_url == fallback_url:
                guess_slug = query.title().replace(" ", "_")
                target_url = f"https://fandom.com{guess_slug}"

            async with session.get(target_url, headers=headers, timeout=6) as content_response:
                if content_response.status != 200: return "", fallback_url
                page_html = await content_response.text()
                
                page_soup = BeautifulSoup(page_html, 'html.parser')
                content_div = page_soup.find('div', class_='mw-parser-output')
                if content_div:
                    paragraphs = []
                    for element in content_div.find_all(['p', 'h2', 'h3', 'li']):
                        text = element.get_text(" ", strip=True)
                        if text and len(text) > 10: paragraphs.append(text)
                    return " ".join(paragraphs[:15])[:3800], target_url
                return "", target_url
    except Exception: return "", fallback_url

# ----------------------------------------------------
# 🎨 MULTIMODAL INVENTORY VISION MATRIX
# ----------------------------------------------------
async def process_multimodal_inventory_suggestion(
    user_question: str, username: str, image_bytes: bytes, content_type: str, market_json: str
) -> str:
    if not AI_API_KEY: return "❌ Missing target AI_API_KEY credentials."
    url = f"https://googleapis.com{AI_API_KEY}"
    
    system_prompt = (
        f"You are Blox Grandmaster AI Intelligence. A user named '{username}' attached an image of their "
        f"inventory and asked: '{user_question}'. Use the live marketplace logs to provide trading advice: \n"
        f"--- LIVE MARKET DATA ---\n{market_json}\n------------------------\n"
        f"Give structural hold/trade recommendations and keep the answer clear and under 5 sentences."
    )

    import base64
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    payload = {"contents": [{"parts": [{"text": system_prompt}, {"inlineData": {"mimeType": content_type, "data": base64_image}}]}], "generationConfig": {"maxOutputTokens": 450}}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=12) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    return res['candidates']['content']['parts']['text'].strip()
    except Exception: pass
    return "Haki vision processing error. Ensure the image upload is legible."

# ----------------------------------------------------
# ⚙️ INTERACTIVE EMBED GENERATORS (Author Branding)
# ----------------------------------------------------
async def apply_designer_author_branding(embed: discord.Embed):
    try:
        designer = await bot.fetch_user(DESIGNER_USER_ID)
        if designer:
            embed.set_author(name=f"Blox Grandmaster Broker Engine", icon_url=designer.display_avatar.url)
            current_footer = embed.footer.text or "Live Matrix Sync"
            embed.set_footer(text=f"{current_footer} • Coded by {designer.name}", icon_url=designer.display_avatar.url)
    except Exception:
        embed.set_footer(text="Cosmic Values Live Matrix Sync • Coded by System Designer")

def build_value_embed(data: Dict[str, str]) -> Tuple[discord.Embed, discord.ui.View]:
    embed = discord.Embed(title=f"Blox Grandmaster AI Intelligence", description=f"**Live Values Profile • {data['name']}**", color=discord.Color.from_rgb(47, 49, 54))
    embed.add_field(name="🔹 Physical Trade Value", value=data['trade_val'], inline=True)
    embed.add_field(name="✨ Permanent Value", value=data['perm_val'], inline=True)
    embed.add_field(name="🔥 Demand", value=data['demand'], inline=True)
    embed.add_field(name="🛡️ Classification", value=data['rarity'], inline=True)
    embed.add_field(name="Market Trend", value=data['trend'], inline=True)
    embed.set_footer(text="🔗 Cosmic Values Matrix")
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Open Database Reference", url="https://bloxfruitsvalues.com", style=discord.ButtonStyle.link))
    return embed, view
