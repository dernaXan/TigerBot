import firebase_admin
from firebase_admin import credentials, db
import discord

class FirebaseDB:
    def __init__(self, db_url: str, cred_path: str, server_defaults: dict = None, user_defaults: dict = None):
        self.cred = credentials.Certificate(cred_path)
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(self.cred, {
                'databaseURL': db_url
            })
        self.root = db.reference("/")
        self.server_defaults = server_defaults or {}
        self.user_defaults = user_defaults or {}

        # Verhindern, dass {} abgespeichert wird -> stattdessen {"_": True}
        if not self.server_defaults:
            self.server_defaults = {"_init": True}
        if not self.user_defaults:
            self.user_defaults = {"_init": True}

    def set(self, path: str, value):
        # leeres dict vermeiden
        if isinstance(value, dict) and len(value) == 0:
            value = {"_init": True}
        ref = self.root.child(path)
        ref.set(value)

    def get(self, path: str):
        ref = self.root.child(path)
        return ref.get()

    def update(self, path: str, value: dict):
        # leeres dict vermeiden
        if isinstance(value, dict) and len(value) == 0:
            return
        ref = self.root.child(path)
        ref.update(value)

    def delete(self, path: str):
        ref = self.root.child(path)
        ref.delete()

    async def init(self, bot: discord.Bot):
        """
        Initialisiert die Datenbankstruktur:
        - Für jede Guild einen Servereintrag
        - Für jeden User in jeder Guild einen Usereintrag
        """
        print(self.server_defaults)
        for guild in bot.guilds:
            server_path = f"servers/{guild.id}"
            # Server eintragen
            if not self.get(server_path):
                self.set(server_path, {"data": self.server_defaults, "users": {"_init": True}})
            else:
                self.update(f"{server_path}/data", self.server_defaults)

            for member in guild.members:
                if member.bot:
                    continue
                user_path = f"{server_path}/users/{member.id}"
                if not self.get(user_path):
                    self.set(user_path, self.user_defaults)
                else:
                    # neue keys hinzufügen, ohne existierende zu löschen
                    current_data = self.get(user_path) or {}
                    for key, value in self.user_defaults.items():
                        if key not in current_data:
                            current_data[key] = value
                    self.set(user_path, current_data)
