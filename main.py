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
# Optional: If you want to use an external AI API later, drop your key here
AI_API_KEY = os.getenv("AI_API_KEY") 

# Preserved Wiki & Fruit Catalogs
WIKI_CATEGORIES: Dict[str, Dict[str, str]] = {
    "Swords": {"⚔️ True Triple Katana Crafting": "True_Triple_Katana"}
}

intents = discord.Intents.default()
intents.message_content = True  # Crucial for scanning chat back text triggers
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------------------------------------
# 💬 XZVIER-STYLE CHAT BACK ENGINE
# ----------------------------------------------------
async def get_ai_chat_response(user_message: str, username: str) -> str:
    """
    Processes plain-text conversational prompts. 
    Can be easily hooked into Gemini, OpenAI, or a free Chatbot API.
    """
    clean_msg = user_message.lower().strip()
    
    # 1. Custom context-aware localized triggers mimicking Xzvier's sassy personality
    if any(word in clean_msg for word in ["hello", "hi", "hey", "yo"]):
        return f"Yo {username}! 🏴‍☠️ What's the plan today? Grinding levels, hunting Sea Beasts, or checking the stock?"
    
    if "best fruit" in clean_msg:
        return "Honestly? **Kitsune** for absolute PvP brainrot, **Buddha** if you actually want to get your grinding done, and **Dragon** if you are hoarding physical value values for trades! 🦊"
    
    if "wfl" in clean_msg or "trade" in clean_msg:
        return "If you want me to calculate a trade value, use my `/trade_calc` or `.wfl` command so I can do the exact math for you! ⚖️"
        
    if any(word in clean_msg for word in ["help", "commands", "cmds"]):
        return "I can do a ton of things! Check out `/blox_info` to search the live wiki, `/stock` to see current fruits on sale, or `/trade_calc` to check your trade offers!"

    # 2. OPTIONAL: External Cloud API Call Fallback (Uncomment & configure if you have a endpoint key)
    # if AI_API_KEY:
    #     try:
    #         async with aiohttp.ClientSession() as session:
    #             payload = {"contents": [{"parts": [{"text": f"You are a helpful, casual Blox Fruits Discord assistant named Master Bot. Answer this query cleanly: {user_message}"}]}]}
    #             async with session.post(f"https://googleapis.com{AI_API_KEY}", json=payload) as resp:
    #                 if resp.status == 200:
    #                     result = await resp.json()
    #                     return result['candidates'][0]['content']['parts'][0]['text']
    #     except Exception as e:
    #         logger.error(f"External Chat AI API error: {e}")

    # 3. Default randomized organic conversational responses
    import random
    fallbacks = [
        f"I hear you, {username}. But standard chat won't find a Mirage Island. Need me to look up wiki stats with `/blox_info` instead? 🏝️",
        "My observation haki is active! What fruit are we hunting down right now? 👁️",
        "That's wild! By the way, the fruit dealer changes his inventory every 4 hours. Don't forget to run `/stock check` to verify drops! 🛒",
        "Interesting point... though I'd rather spend my Beli upgrading my swords at the Blacksmith! ⚔️"
    ]
    return random.choice(fallbacks)

# ----------------------------------------------------
# 🤖 BOT DISPATCH EVENT HANDLER
# ----------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    # Ignore automatic bot webhooks completely to eliminate endless infinite response loops
    if message.author.bot:
        return

    # Check if the bot was explicitly mentioned OR replied to directly via message referencing
    is_mentioned = bot.user in message.mentions
    is_reply_to_me = message.reference and message.reference.cached_message and message.reference.cached_message.author == bot.user
    
    # Process prefix commands normally first if they start with standard symbols (e.g. !fruit)
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # Trigger chat back sequences if they targeted the bot directly
    if is_mentioned or is_reply_to_me:
        # Clean text payload by removing the raw bot client mention ping string (e.g. <@1234455>)
        clean_content = re.sub(r'<@!?\d+>', '', message.content).strip()
        
        # Emulate authentic human conversation workflows using Discord's asynchronous typing block indicators
        async with message.channel.typing():
            response_text = await get_ai_chat_response(clean_content, message.author.display_name)
            
            # Post response threading it as a neat direct inline reply map reference anchor
            await message.reply(response_text)
            return

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        logger.info("Application trees updated with structural layout variables.")
    except Exception as e:
        logger.error(f"Sync error: {e}")

if __name__ == "__main__":
    if not TOKEN: sys.exit("[ERROR] Run token missing.")
    bot.run(TOKEN)
