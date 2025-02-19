import logging
import sqlite3
from datetime import datetime

import websocket
from websocket import WebSocketApp

from twitchapi.auth import AuthServer
from twitchapi.utils import TwitchEndpoint
import json


# message_db = sqlite3.connect('TwitchDatabase/message.db')
# follower_db = sqlite3.connect('TwitchDatabase/follower.db')

class EventSub(WebSocketApp):

    def __init__(self, bot_id:str, channel_id:str, subscription_types:list[str], auth_server:AuthServer):
        super().__init__(url=TwitchEndpoint.TWITCH_WEBSOCKET_URL, on_message=self.on_message)
        self.__session_id = None
        self.__auth = auth_server
        self._bot_id = bot_id
        self._channel_id = channel_id
        self._subscription_types = subscription_types

        self._last_message_date=None

    def on_message(self, ws, message):
        logging.debug("Message received:" + message)
        data = json.loads(message)

        metadata = data["metadata"]
        payload = data["payload"]

        message_type = metadata["message_type"]
        self._last_message_date = datetime.strptime(metadata["message_timestamp"][:-4], "%Y-%m-%dT%H:%M:%S.%f")

        match message_type:
            case "session_welcome":
                self.__session_id = payload["session"]["id"]
                for subscription in self._subscription_types:
                    match subscription:
                        case "channel.chat.message":
                            logging.info("Subscription to get chat message")
                            condition = {"broadcaster_user_id": self._channel_id, "user_id": self._bot_id}
                            self.__subscription(subscription_type=subscription, condition=condition)
            case "notification":
                subscription_type = payload["subscription"]["type"]
                match subscription_type:
                    case "channel.chat.message":
                        event = payload["event"]
                        user_name = event["chatter_user_login"]
                        msg = event["message"]["text"]
                        logging.info(f"{user_name} say : '{msg}'")

    def on_error(self, ws, message):
        logging.error(message)

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("Close websocket")

    def on_open(self, ws):
        logging.info(f"Connect to {TwitchEndpoint.TWITCH_WEBSOCKET_URL}")

    def __subscription(self, subscription_type: str, condition: dict[str, str]):
        logging.info(f"Subscription for {subscription_type}")
        data = {
            "type": subscription_type,
            "version": "1",
            "condition": condition,
            "transport": {
                "method": "websocket",
                "session_id": self.__session_id
            }
        }
        self.__auth.post_request(TwitchEndpoint.EVENTSUB_SUBSCRIPTION, data=data)