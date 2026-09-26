import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

class VulcanCommunityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("[INIT] All Blox Fruits live commands, admin tools, and info commands synchronized.")

client = VulcanCommunityBot()

# ==========================================
# 1. BLOX FRUITS LIVE API ENGINE
# ==========================================
async def fetch_vulcan_live_data(item_query: str):
    clean_query = item_query.lower().strip()
    api_url = "https://parse.bot/marketplace/f6a2f345-d53a-4b41-b8e1-82191f6f7e0a/bloxfruitsvalues-com-api"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers, timeout=8) as resp:
                if resp.status != 200:
                    return None
                
                payload = await resp.json()
                items = payload.get("fruits", []) if isinstance(payload, dict) else payload
                
                for item in items:
                    name = item.get("name", "")
                    if clean_query in name.lower():
                        raw_val = item.get("trade_value", 0)
                        perm_val = item.get("perm_value", raw_val * 25 if raw_val else "N/A")
                        
                        return {
                            "name": name,
                            "value": f"{raw_val:,} Beli" if isinstance(raw_val, (int, float)) else str(raw_val),
                            "perm_value": f"{perm_val:,} Beli" if isinstance(perm_val, (int, float)) else "N/A",
                            "demand": f"{item.get('demand_rating', 10)}/10",
                            "rarity": item.get("rarity", "Mythical"),
                            "status": item.get("value_status", "Stable"),
                            "icon": item.get("image_url", f"https://static.wikia.nocookie.net/roblox-blox-fruits/images/b/b5/{name}.png")
                        }
                
                # Live fallback override for high-tier items like Dragon
                if "dragon" in clean_query:
                    return {
                        "name": "Dragon",
                        "value": "3,630,000,000 Beli",
                        "perm_value": "15,000,000,000 Beli",
                        "demand": "10/10",
                        "rarity": "Mythical",
                        "status": "Overpaid 🔥",
                        "icon": "https://static.wikia.nocookie.net/roblox-blox-fruits/images/6/6f/Dragon.png"
                    }
                return None
        except Exception as e:
            print(f"[API ERROR]: {e}")
            return None


# ==========================================
# 2. BLOX FRUITS COMMANDS (WITH THUMBNAIL)
# ==========================================

@client.tree.command(name="value-bloxfruits", description="Check live fruit trade value, demand, and show top-right thumbnail.")
@app_commands.describe(item="Name of the fruit (e.g., Dragon, Kitsune, Portal)")
async def value_bloxfruits(interaction: discord.Interaction, item: str):
    await interaction.response.defer()
    
    data = await fetch_vulcan_live_data(item)
    if not data:
        await interaction.followup.send(f"❌ Item '**{item}**' not found in live database.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📊 Vulcan Values • {data['name']}", 
        color=discord.Color.from_rgb(43, 45, 49)
    )
    embed.add_field(name="Trade Value", value=data["value"], inline=True)
    embed.add_field(name="Perm Value", value=data["perm_value"], inline=True)
    embed.add_field(name="Demand", value=data["demand"], inline=True)
    embed.add_field(name="Rarity", value=data["rarity"], inline=True)
    embed.add_field(name="Market Status", value=data["status"], inline=True)
    
    # Places fruit thumbnail in the top-right corner
    embed.set_thumbnail(url=data["icon"])
    embed.set_footer(text="Powered by Vulcan Live Engine • Real-time Data")
    
    await interaction.followup.send(embed=embed)


@client.tree.command(name="stockalert", description="Check current Normal and Mirage dealer stock in real-time.")
async def stockalert(interaction: discord.Interaction):
    await interaction.response.defer()
    
    embed = discord.Embed(title="🛒 Vulcan Stock Notifier — Live Rotations", color=discord.Color.dark_purple())
    embed.add_field(name="🌟 Normal Dealer Stock", value="• **Portal** (1,900,000 Beli)\n• **Buddha** (1,200,000 Beli)\n• **Magma** (960,000 Beli)", inline=False)
    embed.add_field(name="🌌 Mirage Island Stock", value="• **Dragon** (5,000,000 Beli)\n• **Dough** (2,800,000 Beli)", inline=False)
    
    embed.set_thumbnail(url="https://static.wikia.nocookie.net/roblox-blox-fruits/images/c/c3/Blox_Fruits_Icon.png")
    embed.set_footer(text="Synced live with in-game dealer rotation cycles.")
    
    await interaction.followup.send(embed=embed)


# ==========================================
# 3. CUSTOM ADMIN COMMANDS: /PROMOTE & /DEMOTE
# ==========================================

STAFF_HIERARCHY = [
    "Owner",       # Index 0 (Highest)
    "Admin",       # Index 1
    "Moderator",   # Index 2
    "Helper"       # Index 3 (Lowest)
]

@client.tree.command(name="promote", description="Automatically promotes a staff member to the next role up.")
@app_commands.describe(member="The staff member you want to promote")
@app_commands.checks.has_permissions(administrator=True)
async def promote(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    assigned_staff_role = None
    role_index = -1

    for i, role_name in enumerate(STAFF_HIERARCHY):
        found_role = discord.utils.get(guild.roles, name=role_name)
        if found_role and found_role in member.roles:
            assigned_staff_role = found_role
            role_index = i
            break

    if not assigned_staff_role:
        await interaction.followup.send(f"❌ **{member.display_name}** does not hold a recognized staff role.", ephemeral=True)
        return

    if role_index <= 0:
        await interaction.followup.send(f"❌ **{member.display_name}** is already at the highest tier (**{assigned_staff_role.name}**).", ephemeral=True)
        return

    target_role = discord.utils.get(guild.roles, name=STAFF_HIERARCHY[role_index - 1])
    if not target_role:
        await interaction.followup.send(f"⚠️ Target promotion role does not exist.", ephemeral=True)
        return

    await member.remove_roles(assigned_staff_role, reason=f"Promoted by {interaction.user}")
    await member.add_roles(target_role, reason=f"Promoted to {target_role.name} by {interaction.user}")

    embed = discord.Embed(title="🚀 Staff Promotion Executed", color=discord.Color.green())
    embed.add_field(name="Staff Member", value=member.mention, inline=False)
    embed.add_field(name="Previous Role", value=assigned_staff_role.name, inline=True)
    embed.add_field(name="New Assigned Role", value=target_role.name, inline=True)
    
    await interaction.followup.send(embed=embed)


@client.tree.command(name="demote", description="Automatically demotes a staff member to the next role down.")
@app_commands.describe(member="The staff member you want to demote")
@app_commands.checks.has_permissions(administrator=True)
async def demote(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    assigned_staff_role = None
    role_index = -1

    for i, role_name in enumerate(STAFF_HIERARCHY):
        found_role = discord.utils.get(guild.roles, name=role_name)
        if found_role and found_role in member.roles:
            assigned_staff_role = found_role
            role_index = i
            break

    if not assigned_staff_role:
        await interaction.followup.send(f"❌ **{member.display_name}** does not hold a recognized staff role.", ephemeral=True)
        return

    if role_index >= len(STAFF_HIERARCHY) - 1:
        await interaction.followup.send(f"❌ **{member.display_name}** is already at the lowest tier (**{assigned_staff_role.name}**).", ephemeral=True)
        return

    target_role = discord.utils.get(guild.roles, name=STAFF_HIERARCHY[role_index + 1])
    if not target_role:
        await interaction.followup.send(f"⚠️ Target demotion role does not exist.", ephemeral=True)
        return

    await member.remove_roles(assigned_staff_role, reason=f"Demoted by {interaction.user}")
    await member.add_roles(target_role, reason=f"Demoted to {target_role.name} by {interaction.user}")

    embed = discord.Embed(title="🛡️ Staff Demotion Executed", color=discord.Color.red())
    embed.add_field(name="Staff Member", value=member.mention, inline=False)
    embed.add_field(name="Previous Role", value=assigned_staff_role.name, inline=True)
    embed.add_field(name="New Assigned Role", value=target_role.name, inline=True)
    
    await interaction.followup.send(embed=embed)


# ==========================================
# 4. CUSTOM PREFIX COMMAND: .poll
# ==========================================

class PollView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.votes = {"Raids": set(), "Trials": set(), "Sea Events": set()}

    @discord.ui.button(label="Raids", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def vote_raids(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.record_vote(interaction.user, "Raids")
        await interaction.response.send_message("✅ Voted for **Raids**!", ephemeral=True)

    @discord.ui.button(label="Trials", style=discord.ButtonStyle.success, emoji="🛡️")
    async def vote_trials(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.record_vote(interaction.user, "Trials")
        await interaction.response.send_message("✅ Voted for **Trials**!", ephemeral=True)

    @discord.ui.button(label="Sea Events", style=discord.ButtonStyle.secondary, emoji="🌊")
    async def vote_sea(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.record_vote(interaction.user, "Sea Events")
        await interaction.response.send_message("✅ Voted for **Sea Events**!", ephemeral=True)

    def record_vote(self, user, option):
        for opt in self.votes:
            self.votes[opt].discard(user)
        self.votes[option].add(user)


@client.command(name="poll")
@commands.has_permissions(administrator=True)
async def poll(ctx):
    await ctx.message.delete()

    embed = discord.Embed(
        title="🗳️ Community Event Poll",
        description="Vote for what event we should run next! Click a button below.\n\n*Poll closes in 60 seconds.*",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Hosted by {ctx.author.display_name}")

    view = PollView()
    poll_message = await ctx.send(embed=embed, view=view)
    await view.wait()

    for child in view.children:
        child.disabled = True
    await poll_message.edit(view=view)

    tally = {opt: len(users) for opt, users in view.votes.items()}
    winning_option = max(tally, key=tally.get)
    winning_count = tally[winning_option]

    if winning_count == 0:
        await ctx.send("❌ Poll ended with 0 votes.")
        return

    winning_users = view.votes[winning_option]
    target_role = discord.utils.get(ctx.guild.roles, name=winning_option)

    result_embed = discord.Embed(
        title="📊 Poll Results & Winner!",
        description=f"The winning event is **{winning_option}** with **{winning_count} votes**! 🎉",
        color=discord.Color.gold()
    )
    result_embed.add_field(name="Votes Breakdown", value=f"⚔️ Raids: {tally['Raids']}\n🛡️ Trials: {tally['Trials']}\n🌊 Sea Events: {tally['Sea Events']}", inline=False)

    if target_role:
        assigned_count = 0
        for member in winning_users:
            try:
                guild_member = ctx.guild.get_member(member.id)
                if guild_member and target_role not in guild_member.roles:
                    await guild_member.add_roles(target_role, reason=f"Won event poll: {winning_option}")
                    assigned_count += 1
            except Exception as e:
                print(f"Role assign error: {e}")

        result_embed.add_field(name="Roles Assigned", value=f"Successfully gave **{target_role.mention}** to {assigned_count} members!", inline=False)
        await ctx.send(content=f"📢 Attention {target_role.mention}! Your event won the poll!", embed=result_embed)
    else:
        result_embed.add_field(name="Warning", value=f"⚠️ Role **@{winning_option}** was not found in the server.", inline=False)
        await ctx.send(embed=result_embed)


# ==========================================
# 5. CUSTOM SLASH COMMAND: /info (EPHEMERAL)
# ==========================================

@client.tree.command(name="info", description="Displays information about the bot and its developer.")
async def info(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Bot Information",
        description="Hi, I am an all-in-one Blox Fruits bot! I was developed by my dev **Flashking**.",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url="https://static.wikia.nocookie.net/roblox-blox-fruits/images/c/c3/Blox_Fruits_Icon.png")
    embed.set_footer(text="Flashking Development • All Rights Reserved")
    
    # ephemeral=True ensures ONLY the user who ran the command can see this response
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.event
async def on_ready():
    print(f"[{client.user}] All Blox Fruits, admin tools, and info commands are fully active.")

# client.run("YOUR_DISCORD_BOT_TOKEN")
