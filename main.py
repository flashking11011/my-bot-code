from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import random
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple
import uuid

import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types

# =========================================================
# 1. CONFIGURATION & LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] StaffSecurityBot: %(message)s",
)
logger = logging.getLogger("StaffSecurityBot")

TOKEN = (
    os.getenv("SECURITY_BOT_TOKEN")
    or os.getenv("DISCORD_TOKEN")
    or "YOUR_BOT_TOKEN_HERE"
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY_HERE"
DB_PATH = os.getenv("SECURITY_DB_PATH", "security_guard.db")

LOG_CHANNEL_ID = 123456789012345678  # Staff log channel ID
STAFF_CHAT_ID = 123456789012345678  # Staff chat channel ID for Sus Alerts
STAFF_ROLE_ID = 123456789012345678  # Role ID of your @team / @Staff role
DEFAULT_PREFIX = "."
TICKET_CATEGORY_NAME = "Support Tickets"

WARNINGS_FILE = "warnings.json"
STAFF_STATS_FILE = "staff_stats.json"
CONFIG_FILE = "config.json"
SUS_FILE = "sus_members.json"
RULES_FILE = "server_rules.json"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

BRO_SYSTEM_PROMPT = """
You are a chill, laid-back senior Discord moderator and best bro helping the server staff team.
- Language: Speak fluent Hinglish (mix of Hindi/Urdu and English) or English depending on whatever the user writes in. If they speak Hinglish (e.g., "bhai", "yaar", "kya karu"), reply in natural Hinglish!
- Vibe & Tone: Talk like a real close friend/bro. Be casual, supportive, funny, and use mild natural swearing/slang (like "damn", "hell", "bullshit", "crap", "bakwas", "scene", "chill kar bro") without being hateful or toxic.
- Moderation Knowledge: Give practical, fair Discord moderation advice. Always preach equality (even if admin/owner friends break rules, screenshot proof first, punish normally with .w or .t, and don't argue in public chat).
- Security Guard Knowledge: Remind staff that dangerous actions (bans, kicks, deleting roles/channels/emojis/webhooks, adding bots) are locked behind Server Owner DM approval via /guard or .guard.
- Bot Commands You Know: .w (warn), .ws (warnings), .t (mute), .ut (unmute), .p (purge), .l (lock), .ul (unlock), .sl (sus list), .rl (rules), .ss (staff stats), .guard (protected actions).
- Keep replies concise, punchy, and easy to read in Discord (under 150 words unless asked for a detailed guide).
"""

MOD_TIPS = [
    "**Don't take the bait, bro:** Trolls want you mad. Stay chill, drop the `.w` or `.t`, and let them cry in timeout.",
    "**Log your damn reasons:** Always put a real reason on `.w`, `.t`, and `.guard` requests so the rest of the boys aren't guessing what happened.",
    "**Cool 'em down first:** If two idiots are beefing in general, a quick 5m `.t` shuts that crap down way faster than arguing.",
    "**Check `.ws` before swinging the hammer:** Always peep `.ws @user` first to see if it's a one-off slip or a repeat clown.",
    "**Hit `.l` when hell breaks loose:** If a raid hits, lock the channel with `.l` first, then submit `.guard ban` requests.",
    "**What happens in staff chat stays in staff chat:** Never leak internal mod talk or warn logs to regular members—that's weak.",
    "**Tag out if you're tilted:** If some annoying kid is getting on your nerves, let another mod handle their ass and grab a drink.",
]

MOD_PLAYBOOKS = {
    "dos": {
        "title": "✅ Mod DO's & ❌ DON'Ts (No-BS Edition)",
        "do": (
            "• **DO** keep a cool head, even when members are acting like total clowns.\n"
            "• **DO** check `.ws @user` and `.sl` before escalating punishments.\n"
            "• **DO** smash `.l` (lock) if chat goes completely off the rails.\n"
            "• **DO** treat everyone the same—even admin/owner homies."
        ),
        "dont": (
            "• **DON'T** power-trip or flex your mod badge over petty crap.\n"
            "• **DON'T** manually delete roles/channels or try other bots—Security Guard will strip your perms.\n"
            "• **DON'T** let buddies slide on rules that regular members get punished for.\n"
            "• **DON'T** wipe evidence before grabbing a screenshot."
        ),
    },
    "friends": {
        "title": "⚖️ Playbook: Admin / Owner Homies Acting Up",
        "do": (
            "1. **Don't be scared to punish 'em:** Drop the exact same `.w` or `.t` anyone else would get. Real owners hate biased servers.\n"
            "2. **Screenshot that bullshit FIRST:** Grab clear screenshots before deleting messages so they can't twist the story.\n"
            "3. **Keep it short in public:** If they pull the *'bro I know the owner'* card, just say *'Rules apply to everyone'* and dip.\n"
            "4. **Drop receipts in Staff Chat:** Ping the admin/owner with the screenshot so they know what their friend was pulling."
        ),
        "dont": (
            "• **DON'T** look the other way—favoritism kills a server fast as hell.\n"
            "• **DON'T** argue about who they're friends with in general chat."
        ),
    },
    "raid": {
        "title": "🛡️ Playbook: Raid Defense",
        "do": (
            "1. Immediately run `.l` in the channels getting flooded.\n"
            "2. Run `.p 50` to wipe all that spam crap.\n"
            "3. Use `.guard ban @user Raid` to send ban approvals to the Owner.\n"
            "4. Ping `@team` if they're hitting multiple channels."
        ),
        "dont": (
            "• **DON'T** talk to raiders—they're bored trolls looking for reactions.\n"
            "• **DON'T** unlock (`.ul`) until the raid is cleared."
        ),
    },
    "toxicity": {
        "title": "🔥 Playbook: Beef & Toxic Drama",
        "do": (
            "1. Step in early: *'Yo, drop it and move on.'*\n"
            "2. If they keep yapping, warn both with `.w @user Ignoring staff`.\n"
            "3. Still going? Give 'em a 15m timeout (`.t @user 15 Chill out`)."
        ),
        "dont": (
            "• **DON'T** pick sides in public chat.\n"
            "• **DON'T** manually ban without Owner approval."
        ),
    },
    "appeal": {
        "title": "📩 Playbook: Punishment Appeals",
        "do": (
            "1. Check `.ws @user` and logs to see what stupid thing they actually did.\n"
            "2. Check `.sl` to see if they're already flagged on the Sus List.\n"
            "3. Ask the mod who punished them before lifting anything."
        ),
        "dont": (
            "• **DON'T** unmute (`.ut`) another mod's punish behind their back—that's bad teammate etiquette."
        ),
    },
}

STAFF_FUN = [
    "😂 **Bro Joke:** Why did the Discord mod bring a ladder to the server? Because the bullshit in general was on another level.",
    "☕ **Bro Check:** Drink some damn water, fix your shrimp posture, and take a breath.",
    "🎲 **Staff Icebreaker:** Be honest—who's the most dramatic regular member in this server right now?",
    "🧠 **Mod Trivia:** How many warns/mutes in 7 days puts someone's ass on the Sus Tracker? *(Answer: 2!)*",
    "👊 **Respect, bro:** Dealing with trolls all day is exhausting as hell, seriously appreciate you holding the server down.",
    "😂 **Bro Joke:** What's a tired moderator's favorite combo? `Ctrl + Alt + Ban`.",
]

# =========================================================
# 2. SQLITE SECURITY DATABASE & JSON STAFF STORAGE
# =========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                request_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                guild_name TEXT,
                admin_id INTEGER,
                admin_name TEXT,
                admin_avatar TEXT,
                action_type TEXT,
                action_display TEXT,
                target_id TEXT,
                target_name TEXT,
                reason TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT,
                resolved_at TEXT,
                owner_id INTEGER,
                decision_notes TEXT,
                extra_data TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                executor_id INTEGER,
                executor_name TEXT,
                event_type TEXT,
                details TEXT,
                is_authorized INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quarantined_bots (
                bot_id INTEGER PRIMARY KEY,
                bot_name TEXT,
                guild_id INTEGER,
                inviter_id INTEGER,
                inviter_name TEXT,
                quarantined_at TEXT,
                status TEXT DEFAULT 'QUARANTINED',
                notes TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stopped_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                guild_id INTEGER,
                action_attempted TEXT,
                target_name TEXT,
                removed_roles TEXT,
                reason TEXT,
                stopped_at TEXT,
                status TEXT DEFAULT 'DEMOTED'
            )
        """)
    conn.close()


init_db()


def load_json(filename: str) -> dict:
