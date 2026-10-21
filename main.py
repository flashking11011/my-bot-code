import os
import sys
import logging
import json
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] BloxFruitsBot: %(message)s")
logger = logging.getLogger("BloxFruitsBot")

TOKEN = os.getenv("BLOX_FRUITS_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")

# Preserved Wiki & Fruit Catalogs
WIKI_CATEGORIES: Dict[str, Dict[str, str]] = {
    "Swords": {"⚔️ True Triple Katana Crafting": "True_Triple_Katana"}
}

intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------------------------------------
# 🔍 WIKI SCRAPER & DATA PARSER
# ----------------------------------------------------
async def fetch_wiki_summary(page_title: str) -> tuple[str, str]:
    """
    Scrapes the Blox Fruits Wiki page to retrieve a summary paragraph and a primary thumbnail image.
    """
    base_url = f"https://fandom.com{page_title}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    return f"Couldn't connect to the wiki page. (HTTP {response.status})", ""
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # Extract the primary image thumbnail
                img_tag = soup.find("img", class_="pi-image-thumbnail") or soup.find("meta", property="og:image")
                img_url = ""
                if img_tag:
                    img_url = img_tag.get("src") if img_tag.name == "img" else img_tag.get("content", "")
                
                # Extract first meaningful text paragraph (skipping infobox fields or empty lines)
                content_div = soup.find("div", class_="mw-parser-output")
                if not content_div:
                    return "Wiki page structure could not be parsed.", img_url
                    
                paragraphs = content_div.find_all("p", recursive=False)
                summary = ""
                for p in paragraphs:
                    text = p.get_text().strip()
                    # Filter out short tracking snippets or empty elements
                    if len(text) > 40 and not text.startswith("{"):
                        # Strip Wikipedia citation brackets like, [2]
                        summary = re.sub(r'\[\d+\]', '', text)
                        break
                
                if not summary:
                    summary = "No introductory description found on this wiki entry."
                    
                return summary, img_url
    except Exception as e:
        logger.error(f"Wiki scraping engine error: {e}")
        return "An internal timeout or connection error occurred while querying the wiki database.", ""

# ----------------------------------------------------
# 🤖 PRODUCTION COMMAND OVERLAYS
# ----------------------------------------------------
@bot.tree.command(name="blox_info", description="Look up items, swords, or guides directly from the Blox Fruits Wiki!")
@app_commands.describe(query="What item or game page do you want to look up?")
async def blox_info(interaction: discord.Interaction, query: str):
    # Immediate response deferral to allow up to 15 minutes of compute processing time for web scraping
    await interaction.response.defer(thinking=True)
    
    # Check if user query matches shorthand labels in WIKI_CATEGORIES, otherwise format string directly for URL insertion
    target_page = query.strip().replace(" ", "_")
    display_title = query.title()
    
    for category, items in WIKI_CATEGORIES.items():
        for custom_label, raw_link in items.items():
            if query.lower() in custom_label.lower() or query.lower() in raw_link.lower():
                target_page = raw_link
                display_title = custom_label
                break

    # Execute asynchronous web scraper
    summary_text, image_thumbnail = await fetch_wiki_summary(target_page)
    
    # Generate clean professional Discord Embed interface
    embed = discord.Embed(
        title=f"📖 Wiki Database: {display_title}",
        url=f"https://fandom.com{target_page}",
        description=summary_text if len(summary_text) <= 2048 else f"{summary_text[:2045]}...",
        color=discord.Color.blue()
    )
    
    if image_thumbnail:
        embed.set_thumbnail(url=image_thumbnail)
        
    embed.set_footer(text="Blox Fruits Wiki Assistant • Data pulled live from Fandom")
    
    # Edit the deferred placeholder message with the compiled data package
    await interaction.followup.send(embed=embed)

# ----------------------------------------------------
# 💬 KEEP EXISTING EVENT HANDLERS BELOW
# ----------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        logger.info("Application commands successfully synchronized to active channels.")
    except Exception as e:
        logger.error(f"Sync error: {e}")

if __name__ == "__main__":
    if not TOKEN: sys.exit("[ERROR] Run token missing.")
    bot.run(TOKEN)
