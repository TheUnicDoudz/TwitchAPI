import json
import logging
import os
from datetime import datetime

import requests
from twitchapi.auth import UriServer, REDIRECT_URI, DEFAULT_TIMEOUT
from twitchapi.exception import TwitchAuthentificationError, TwitchEndpointError


class ChatBot:
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    ACCESS_TOKEN_FILE = ".access_token"

    def __init__(self, client_id, client_secret, bot_name, owner_name, redirect_uri=REDIRECT_URI,
                 timeout=DEFAULT_TIMEOUT):
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__uri = UriServer()
        self.__credentials = None

        if not os.path.exists(self.ACCESS_TOKEN_FILE):
            access_token, refresh_token, expire_date = self.__uri.get_access_token(client_id=client_id,
                                                                                   client_secret=client_secret,
                                                                                   scope=["user:read:chat",
                                                                                          "user:write:chat",
                                                                                          "user:bot", "channel:bot"],
                                                                                   redirect_uri=redirect_uri,
                                                                                   timeout=timeout)
            self.__credentials = {"access_token": access_token, "refresh_token": refresh_token,
                                  "expire_date": expire_date}
            with open(self.ACCESS_TOKEN_FILE, "w") as f:
                json.dump(self.__credentials, f)
        else:
            with open(self.ACCESS_TOKEN_FILE, "r") as f:
                self.__credentials = json.load(f)

            if datetime.strptime(self.__credentials["expire_date"], '%d/%m/%Y') <= datetime.now():
                access_token, refresh_token, expire_date = self.__uri.refresh_token(self._client_id,
                                                                                    self.__client_secret,
                                                                                    self.__credentials["refresh_token"])
                self.__credentials = {"access_token": access_token, "refresh_token": refresh_token,
                                      "expire_date": expire_date}
                with open(self.ACCESS_TOKEN_FILE, "w") as f:
                    json.dump(self.__credentials, f)

        self.__headers = {
            "Authorization": f"Bearer {self.__credentials['access_token']}",
            "Client-Id": self._client_id,
            "Content-Type": "application/json"
        }

        self._bot_id = self._get_id(bot_name)
        logging.debug("Bot id: " + self._bot_id)
        self._owner_id = self._get_id(owner_name)
        logging.debug("Owner id: " + self._owner_id)

    def _get_id(self, user_name: str) -> str:
        data = self.__get_request(endpoint="users?login=" + user_name)
        return data['data'][0]['id']

    def __get_request(self, endpoint: str) -> dict:
        url_endpoint = self.TWITCH_ENDPOINT + endpoint
        r = requests.get(url_endpoint, headers=self.__headers)
        if r.status_code != 200:
            if r.status_code == 401:
                self.__refresh_access_token()
                r = requests.get(url_endpoint, headers=self.__headers)
                if r.status_code != 200:
                    logging.info(r.content)
                    raise TwitchAuthentificationError("Something's wrong with the access token!!")
            else:
                raise TwitchEndpointError(
                    f"The url {url_endpoint} is not correct or you don't have the rights to use it!")
        return r.json()

    def __refresh_access_token(self):

        access_token, refresh_token, expire_date = self.__uri.refresh_token(self._client_id, self.__client_secret,
                                                                            self.__credentials["refresh_token"])
        self.__credentials = {"access_token": access_token, "refresh_token": refresh_token, "expire_date": expire_date}
        with open(self.ACCESS_TOKEN_FILE, "w") as f:
            json.dump(self.__credentials, f)

        self.__headers = {
            "Authorization": f"Bearer {self.__credentials['access_token']}",
            "Client-Id": self._client_id,
            "Content-Type": "application/json"
        }
