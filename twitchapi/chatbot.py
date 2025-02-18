import json
import logging
import os
import secrets
from datetime import datetime
from enum import Enum
from random import randint

import requests
from requests import Response

from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT
from twitchapi.exception import TwitchAuthentificationError, TwitchEndpointError, TwitchMessageNotSentWarning
from twitchapi.eventsub import EventSub, REDIRECT_URI_MESSAGE


class TwitchEndpoint(Enum):
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    USER_ID = "users?login="
    SEND_MESSAGE = "chat/messages"
    EVENTSUB_SUBSCRIPTION = "eventsub/subscriptions"


class ChatBot:
    ACCESS_TOKEN_FILE = ".access_token"

    def __init__(self, client_id: str, client_secret: str, bot_name: str, channel_name: str,
                 redirect_uri_auth: str = REDIRECT_URI_AUTH, redirect_uri_message: str = REDIRECT_URI_MESSAGE,
                 timeout=DEFAULT_TIMEOUT):
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__uri = AuthServer()
        self.__event_sub = EventSub()
        self.__credentials = None

        if not os.path.exists(self.ACCESS_TOKEN_FILE):
            access_token, refresh_token, expire_date = self.__uri.get_access_token(client_id=client_id,
                                                                                   client_secret=client_secret,
                                                                                   scope=["user:read:chat",
                                                                                          "user:write:chat",
                                                                                          "user:bot", "channel:bot"],
                                                                                   redirect_uri=redirect_uri_auth,
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
        self._channel_id = self._get_id(channel_name)
        logging.debug("Channel id: " + self._channel_id)

        self.__connect_eventsub_message()

    def _get_id(self, user_name: str) -> str:
        data = self.__get_request(endpoint=TwitchEndpoint.USER_ID.value + user_name)
        return data['data'][0]['id']

    def send_message(self, message: str, reply_message_id: str = None):
        data = {
            "broadcaster_id": self._channel_id,
            "sender_id": self._bot_id,
            "message": message,
        }
        if reply_message_id:
            data["reply_parent_message_id"] = reply_message_id

        add_data = self.__post_request(endpoint=TwitchEndpoint.SEND_MESSAGE.value, data=data)['data'][0]

        if not add_data["is_sent"]:
            logging.warning(f"Message not sent: {add_data['drop_reason']}")
            drop_code = add_data["drop_reason"]["code"]
            drop_message = add_data["drop_reason"]["message"]
            raise TwitchMessageNotSentWarning(f"{drop_code}: {drop_message}")

    def __connect_eventsub_message(self, callback: str = REDIRECT_URI_MESSAGE):
        condition = {
            "type": "channel.chat.message",
            "version": "1",
            "condition": {
                "broadcaster_user_id": self._channel_id,
                "user_id": self._bot_id
            }
        }

        response = self.__connect_evensub(condition)

    def __connect_evensub(self, condition:dict, callback: str = REDIRECT_URI_MESSAGE):
        secret_length = randint(16, 32)
        secret = secrets.token_urlsafe(secret_length)
        data = {
            "transport":{
                "method": "webhook",
                "callback": callback,
                "secret": secret
            }
        }
        data.update(condition)

        add_data = self.__post_request(TwitchEndpoint.EVENTSUB_SUBSCRIPTION.value, data=data)
        return add_data

    def __get_request(self, endpoint: str) -> dict:
        url_endpoint = TwitchEndpoint.TWITCH_ENDPOINT.value + endpoint
        r = self.__check_request(requests.get, url_endpoint)
        return r.json()

    def __post_request(self, endpoint: str, data: dict) -> dict:
        url_endpoint = TwitchEndpoint.TWITCH_ENDPOINT.value + endpoint
        r = self.__check_request(requests.post, url_endpoint, data)
        return r.json()

    def __check_request(self, request_function, url_endpoint: str, data: dict = None) -> Response:
        params = {"url": url_endpoint, "headers": self.__headers}
        if data:
            params["json"] = data
        response = request_function(**params)
        if response.status_code != 200:
            if response.status_code == 401:
                self.__refresh_access_token()
                response = request_function(**params)
                if response.status_code != 200:
                    logging.error(response.content)
                    raise TwitchAuthentificationError("Something's wrong with the access token!!")
            else:
                raise TwitchEndpointError(
                    f"The url {url_endpoint} is not correct or you don't have the rights to use it!")
        return response

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

    def stop_eventsub(self):
        self.__event_sub.stop()
