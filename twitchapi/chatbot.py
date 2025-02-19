import logging

from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT
from twitchapi.exception import TwitchMessageNotSentWarning
from twitchapi.eventsub import EventSub
from twitchapi.utils import TwitchEndpoint



class ChatBot:

    def __init__(self, client_id: str, client_secret: str, bot_name: str, channel_name: str,
                 redirect_uri_auth: str = REDIRECT_URI_AUTH,
                 timeout=DEFAULT_TIMEOUT):
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__uri = AuthServer()
        self.__event_sub = EventSub()
        self.__uri.authentication(client_id=client_id, client_secret=client_secret, scope=["user:read:chat",
         "user:write:chat",
         "user:bot", "channel:bot"], timeout=timeout, redirect_uri=redirect_uri_auth)


        self._bot_id = self._get_id(bot_name)
        logging.debug("Bot id: " + self._bot_id)
        self._channel_id = self._get_id(channel_name)
        logging.debug("Channel id: " + self._channel_id)


    def _get_id(self, user_name: str) -> str:
        data = self.__uri.get_request(endpoint=TwitchEndpoint.USER_ID + user_name)
        return data['data'][0]['id']

    def send_message(self, message: str, reply_message_id: str = None):
        data = {
            "broadcaster_id": self._channel_id,
            "sender_id": self._bot_id,
            "message": message,
        }
        if reply_message_id:
            data["reply_parent_message_id"] = reply_message_id

        add_data = self.__uri.post_request(endpoint=TwitchEndpoint.SEND_MESSAGE, data=data)['data'][0]

        if not add_data["is_sent"]:
            logging.warning(f"Message not sent: {add_data['drop_reason']}")
            drop_code = add_data["drop_reason"]["code"]
            drop_message = add_data["drop_reason"]["message"]
            raise TwitchMessageNotSentWarning(f"{drop_code}: {drop_message}")