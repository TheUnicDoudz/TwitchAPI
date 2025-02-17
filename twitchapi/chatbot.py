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
            token = uri.refresh_access_token(client_id=client_id, scope=["user:read:chat", "user:write:chat"],
                                     redirect_uri=redirect_uri, timeout=timeout)
            with open(self.ACCESS_TOKEN_FILE, "w") as f:
                f.write(token)
        else:
            with open(self.ACCESS_TOKEN_FILE, "r") as f:
                token = f.read()

        self.__headers = {
            "Authorization": f"Bearer {token}",
            "Client-Id": self._client_id
        }

        r = requests.get(f"{self.ID_ENDPOINT}users?login={bot_name}", headers=self.__headers)
        print(r.content)