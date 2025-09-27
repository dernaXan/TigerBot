import discord
from discord.ext import commands
import firebase
import os

cred_path = '/etc/secrets/db_key.json' 
db_url = 'https://tiger-a3c02-default-rtdb.europe-west1.firebasedatabase.app/'
server_defaults = {
    "levels": {
        "enabled": True,
        "xp_per_message": 5,
        "xp_cooldown": 60,
        "level_up_channel": None,
        "level_roles": {},
        "xp_per_level": 100
    }
}
user_defaults = {
    "level": 0,
    "xp": 0,
    "last_message_time": 0
}
firebase_db = firebase.FirebaseDB(db_url, cred_path, server_defaults, user_defaults)

TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True  # Enable access to message content

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    firebase_db.init(bot)
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
                        await channel.send(f"Congratulations {message.author.mention}, you've reached level {new_level}!")

                level_roles = levels_config.get("level_roles", {})
                role_id = level_roles.get(str(new_level))
                if role_id:
                    role = message.guild.get_role(role_id)
                    if role:
                        await message.author.add_roles(role)

    await bot.process_commands(message)