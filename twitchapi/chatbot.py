import json
import os

import requests
from twitchapi.auth import UriServer, REDIRECT_URI, DEFAULT_TIMEOUT


class ChatBot:
    ID_ENDPOINT = "https://api.twitch.tv/helix/"
    ACCESS_TOKEN_FILE = ".access_token"

    def __init__(self, client_id, client_secret, bot_name, owner_name, redirect_uri=REDIRECT_URI,
                 timeout=DEFAULT_TIMEOUT):
        self._client_id = client_id
        self.__client_secret = client_secret

        if not os.path.exists(self.ACCESS_TOKEN_FILE):
            uri = UriServer()
            token, refresh_token = uri.get_access_token(client_id=client_id, client_secret=client_secret, scope=["user:read:chat", "user:write:chat", "user:bot", "channel:bot"],
                                     redirect_uri=redirect_uri, timeout=timeout)
            credentials = {"access_token": token, "refresh_token": refresh_token}
            with open(self.ACCESS_TOKEN_FILE, "w") as f:
                json.dump(credentials, f)
        else:
            with open(self.ACCESS_TOKEN_FILE, "r") as f:
                credentials = json.load(f)

        self.__headers = {
            "Authorization": f"Bearer {credentials['access_token']}",
            "Client-Id": self._client_id,
            "Content-Type": "application/json"
        }

        r = requests.get(f"{self.ID_ENDPOINT}users?login={bot_name}", headers=self.__headers)
        print(r.content)