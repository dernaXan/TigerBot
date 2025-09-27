import discord
from discord.ext import commands
import firebase
import os
import dotenv

cred_path = 'etc/secrets/db_key.json' 
db_url = 'https://tiger-a3c02-default-rtdb.europe-west1.firebasedatabase.app/'
server_defaults = {
    "levels": {
        "enabled": True,
        "xp_per_message": 5,
        "xp_cooldown": 60,
        "level_up_channel": 0,
        "level_roles": {"_init": True},
        "xp_per_level": 100,
        "level_up_message": "Congratulations {user}, you've reached level {level}!"
    },
    "create_vc": 0,
    "supporter_role": 0
}
user_defaults = {
    "level": 0,
    "xp": 0,
    "last_message_time": 0
}
firebase_db = firebase.FirebaseDB(db_url, cred_path, server_defaults, user_defaults)

try:
    dotenv.load_dotenv('etc/secrets/secrets.env')
except:
    print("It seems that we're running in a production environment.")

TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True  # Enable access to message content

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await firebase_db.init(bot)
    print('Logged into Database!')
    synced = await bot.sync_commands()
    print(f'Synced commands!')
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_guild_join(guild):
    server_path = f"servers/{guild.id}"
    if not firebase_db.get(server_path):
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
    else:
        firebase_db.update(f"{server_path}/data", server_defaults)
    for member in guild.members:
        user_path = f"{server_path}/users/{member.id}"
        if not firebase_db.get(user_path):
            firebase_db.set(user_path, user_defaults)
        else:
            firebase_db.update(user_path, user_defaults)

@bot.event
async def on_member_join(member):
    server_path = f"servers/{member.guild.id}"
    user_path = f"{server_path}/users/{member.id}"
    if not firebase_db.get(user_path):
        firebase_db.set(user_path, user_defaults)
    else:
        firebase_db.update(user_path, user_defaults)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    server_path = f"servers/{message.guild.id}"
    user_path = f"{server_path}/users/{message.author.id}"

    user_data = firebase_db.get(user_path)
    if not user_data:
        firebase_db.set(user_path, user_defaults)
        user_data = user_defaults

    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    levels_config = server_data["data"].get("levels", {})
    if levels_config.get("enabled", False):
        import time
        current_time = int(time.time())
        last_message_time = user_data.get("last_message_time", 0)
        xp_cooldown = levels_config.get("xp_cooldown", 60)

        if current_time - last_message_time >= xp_cooldown:
            xp_per_message = levels_config.get("xp_per_message", 5)
            new_xp = user_data.get("xp", 0) + xp_per_message
            new_level = user_data.get("level", 0)

            xp_per_level = levels_config.get("xp_per_level", 100)
            while new_xp >= (new_level + 1) * xp_per_level:
                new_level += 1

            firebase_db.update(user_path, {
                "xp": new_xp,
                "level": new_level,
                "last_message_time": current_time
            })

            if new_level > user_data.get("level", 0):
                level_up_channel_id = levels_config.get("level_up_channel")
                if level_up_channel_id:
                    channel = bot.get_channel(level_up_channel_id)
                    if channel:
                        text = levels_config.get("level_up_message", "Congratulations {user}, you've reached level {level}({xp} XP)!")
                        text = text.replace("{user}", message.author.mention).replace("{level}", str(new_level)).replace("{xp}", str(new_xp))
                        await channel.send(text)

                level_roles = levels_config.get("level_roles", {})
                role_id = level_roles.get(str(new_level), None)
                if role_id:
                    role = message.guild.get_role(role_id)
                    if role:
                        await message.author.add_roles(role)
                        await message.channel.send(f"{message.author.mention} has been given the role {role.name} for reaching level {new_level}!")

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    server_path = f"servers/{member.guild.id}"
    user_path = f"{server_path}/users/{member.id}"

    user_data = firebase_db.get(user_path)
    if not user_data:
        firebase_db.set(user_path, user_defaults)
        user_data = user_defaults

    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    create_vc_channel_id = server_data["data"].get("create_vc", 0)
    if create_vc_channel_id == 0:
        return

    # Auto-VC erstellen, wenn jemand im "create_vc" Channel joint
    if before.channel is None and after.channel is not None:
        if after.channel.id == create_vc_channel_id:
            new_vc = await member.guild.create_voice_channel(
                name=f"{member.name}'s VC",
                category=after.channel.category
            )
            await member.move_to(new_vc)

    # Prüfen, ob ein Auto-VC leer ist → löschen
    if before.channel is not None and len(before.channel.members) == 0:
        # Nur löschen, wenn es ein Auto-VC ist
        if before.channel.name.endswith("'s VC"):
            await before.channel.delete()

class LevelSettingsView(discord.ui.View):
    @discord.ui.button(label="Enable/Disable Levels", style=discord.ButtonStyle.red)
    async def toggle_levels(self, button, interaction):
        server_path = f"servers/{interaction.guild.id}"
        server_data = firebase_db.get(server_path)
        if not server_data:
            firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
            server_data = {"data": server_defaults}

        levels_config = server_data["data"].get("levels", {})
        current_status = levels_config.get("enabled", False)
        new_status = not current_status
        firebase_db.update(f"{server_path}/data/levels", {"enabled": new_status})

        status_text = "enabled" if new_status else "disabled"
        await interaction.response.send_message(f"Levels have been {status_text}.", ephemeral=True)

    @discord.ui.button(label="XP per Message", style=discord.ButtonStyle.blurple)
    async def set_xp_per_message(self, button, interaction):
        cmd = bot.get_application_command("set_xp_per_message")
        if cmd:
            mention = f"</{cmd.name}:{cmd.id}>"
            embed = discord.Embed(title="Set XP per Message", description=f"Set the amount of XP users gain per message with the command {mention}.", color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Set XP per Message", description="Set the amount of XP users gain per message with the command ``/set_xp_per_message``.", color=discord.Color.blue())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="XP Cooldown", style=discord.ButtonStyle.blurple)
    async def set_xp_cooldown(self, button, interaction):
        cmd = bot.get_application_command("set_xp_cooldown")
        if cmd:
            mention = f"</{cmd.name}:{cmd.id}>"
            embed = discord.Embed(title="Set XP Cooldown", description=f"Set the cooldown time (in seconds) between messages that grant XP with the command {mention}.", color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Set XP Cooldown", description="Set the cooldown time (in seconds) between messages that grant XP with the command ``/set_xp_cooldown``.", color=discord.Color.blue())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="XP per Level", style=discord.ButtonStyle.blurple)
    async def set_xp_per_level(self, button, interaction):
        cmd = bot.get_application_command("set_xp_per_level")
        if cmd:
            mention = f"</{cmd.name}:{cmd.id}>"
            embed = discord.Embed(title="Set XP per Level", description=f"Set the amount of XP required to level up with the command {mention}.", color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Set XP per Level", description="Set the amount of XP required to level up with the command ``/set_xp_per_level``.", color=discord.Color.blue())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Level Up Channel", style=discord.ButtonStyle.blurple)
    async def set_level_up_channel(self, button, interaction):
        cmd = bot.get_application_command("set_level_up_channel")
        if cmd:
            mention = f"</{cmd.name}:{cmd.id}>"
            embed = discord.Embed(title="Set Level Up Channel", description=f"Set the channel where level up messages are sent with the command {mention}.", color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Set Level Up Channel", description="Set the channel where level up messages are sent with the command ``/set_level_up_channel``.", color=discord.Color.blue())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Level Roles", style=discord.ButtonStyle.blurple)
    async def set_level_roles(self, button, interaction):
        cmd = bot.get_application_command("set_level_role")
        if cmd:
            mention = f"</{cmd.name}:{cmd.id}>"
            embed = discord.Embed(title="Set Level Roles", description=f"Assign roles to users when they reach a certain level with the command {mention}.", color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Set Level Roles", description="Assign roles to users when they reach a certain level with the command ``/set_level_role``.", color=discord.Color.blue())

        await interaction.response.send_message(embed=embed, ephemeral=True)

class VCChannel_Select(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Wähle einen Channel...", options=options)

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        if channel or channel_id == 0:
            await interaction.response.send_message(f"Selected channel: {channel.name}", ephemeral=True)
            firebase_db.update(f"servers/{interaction.guild.id}/data/", {"create_vc": channel_id})

class VCSettingsView(discord.ui.View):
    def __init__(self, channels):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(label="Disable", value="0"),
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in channels if isinstance(ch, discord.VoiceChannel)
        ]
        self.add_item(VCChannel_Select(options))

class SettingsView(discord.ui.View):
    @discord.ui.select(
        placeholder="Select a settings category",
        options=[
            discord.SelectOption(label="Levels", description="Configure leveling settings"),
            discord.SelectOption(label="Create VC", description="Configure voice channel settings"),
        ]
    )
    async def select_callback(self, select, interaction):
        if select.values[0] == "Levels":
            embed = discord.Embed(title="Level Settings", description="Configure leveling settings below.", color=discord.Color.green())
            view = LevelSettingsView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        elif select.values[0] == "Create VC":
            embed = discord.Embed(title="Create VC Settings", description="Select the channel where users can create temporary voice channels.", color=discord.Color.green())
            channels = interaction.guild.channels
            view = VCSettingsView(channels)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="settings", description="View or change server settings")
async def settings(ctx):
    await ctx.defer()
    embed = discord.Embed(title="Server Settings", description="Select a category to view or change settings.")
    view = SettingsView()
    await ctx.respond(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="set_xp_per_message", description="Set the amount of XP users gain per message")
@commands.has_permissions(administrator=True)
async def set_xp_per_message(ctx, xp: int):
    if xp < 1:
        await ctx.respond("XP per message must be a positive integer.", ephemeral=True)
        return

    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    firebase_db.update(f"{server_path}/data/levels", {"xp_per_message": xp})
    await ctx.respond(f"XP per message has been set to {xp}.", ephemeral=True)

@bot.slash_command(name="set_xp_cooldown", description="Set the cooldown time (in seconds) between messages that grant XP")
@commands.has_permissions(administrator=True)
async def set_xp_cooldown(ctx, seconds: int):
    if seconds < 0:
        await ctx.respond("XP cooldown must be a non-negative integer.", ephemeral=True)
        return

    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    firebase_db.update(f"{server_path}/data/levels", {"xp_cooldown": seconds})
    await ctx.respond(f"XP cooldown has been set to {seconds} seconds.", ephemeral=True)

@bot.slash_command(name="set_xp_per_level", description="Set the amount of XP required to level up")
@commands.has_permissions(administrator=True)
async def set_xp_per_level(ctx, xp: int):
    if xp <= 0:
        await ctx.respond("XP per level must be a positive integer.", ephemeral=True)
        return

    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    firebase_db.update(f"{server_path}/data/levels", {"xp_per_level": xp})
    await ctx.respond(f"XP per level has been set to {xp}.", ephemeral=True)

@bot.slash_command(name="set_level_up_message", description="Set the message that is sent when a user levels up")
@commands.has_permissions(administrator=True)
async def set_level_up_message(ctx, *, message: str):
    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    firebase_db.update(f"{server_path}/data/levels", {"level_up_message": message})
    await ctx.respond("Level up message has been updated.", ephemeral=True)

@bot.slash_command(name="set_level_up_channel", description="Set the channel where level up messages are sent")
@commands.has_permissions(administrator=True)
async def set_level_up_channel(ctx, channel: discord.TextChannel):
    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    firebase_db.update(f"{server_path}/data/levels", {"level_up_channel": channel.id})
    await ctx.respond(f"Level up messages will be sent in {channel.mention}.", ephemeral=True)

@bot.slash_command(name="set_level_role", description="Assign a role to users when they reach a certain level")
@commands.has_permissions(administrator=True)
async def set_level_role(ctx, level: int, role: discord.Role):
    if level <= 0:
        await ctx.respond("Level must be a positive integer.", ephemeral=True)
        return

    server_path = f"servers/{ctx.guild.id}"
    server_data = firebase_db.get(server_path)
    if not server_data:
        firebase_db.set(server_path, {"data": server_defaults, "users": {"_init": True}})
        server_data = {"data": server_defaults}

    levels_config = server_data["data"].get("levels", {})
    level_roles = levels_config.get("level_roles", {})
    level_roles[str(level)] = role.id
    firebase_db.update(f"{server_path}/data/levels", {"level_roles": level_roles})
    await ctx.respond(f"Role {role.name} will be assigned to users when they reach level {level}.", ephemeral=True)

class TicketView(discord.ui.View):
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close_ticket(self, button, interaction):
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await interaction.channel.delete()

class SupportTicketView(discord.ui.View):
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green)
    async def create_ticket(self, button, interaction):
        if not firebase_db.get(f"servers/{interaction.guild.id}/data/supporter_role"):
            await interaction.response.send_message("Support tickets are not configured on this server.", ephemeral=True)
            return
        supporter_role_id = firebase_db.get(f"servers/{interaction.guild.id}/data/supporter_role")
        supporter_role = interaction.guild.get_role(supporter_role_id)
        if not supporter_role:
            await interaction.response.send_message("Supporter role not found. Please contact an administrator.", ephemeral=True)
            return
        channel = interaction.channel
        user = interaction.user
        for thread in channel.threads:
            if thread.name == f"ticket-{user.name}".lower():
                await interaction.response.send_message(f"You already have an open ticket in this channel: {thread.mention}", ephemeral=True)
                return
            
        ticket_thread = await channel.create_thread(name=f"ticket-{user.name}".lower(), type=discord.ChannelType.private_thread, invitable=False)
        await ticket_thread.add_user(user)
        for member in supporter_role.members:
            await ticket_thread.add_user(member)
        embed = discord.Embed(title="Support Ticket", description="A supporter will be with you shortly. To close this ticket, press the button below.", color=discord.Color.blue())
        view = TicketView()
        await ticket_thread.send(f"{user.mention}, your ticket has been created.\n{supporter_role.mention}", embed=embed, view=view)
        

if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("BOT_TOKEN not found in environment!")
    bot.run(TOKEN)