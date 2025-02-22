import logging

from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT
from twitchapi.exception import TwitchMessageNotSentWarning, KillThreadException
from twitchapi.eventsub import EventSub
from twitchapi.utils import TwitchEndpoint, ThreadWithExc, TriggerMap, TriggerSignal

class ChatBot:

    def __init__(self, client_id: str, client_secret: str, bot_name: str, channel_name: str,
                 redirect_uri_auth: str = REDIRECT_URI_AUTH,
                 timeout=DEFAULT_TIMEOUT):
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__auth = AuthServer()
        self.__auth.authentication(client_id=client_id, client_secret=client_secret, scope=["user:read:chat",
         "user:write:chat", "user:bot", "channel:bot"], timeout=timeout, redirect_uri=redirect_uri_auth)


        self._bot_id = self._get_id(bot_name)
        logging.debug("Bot id: " + self._bot_id)
        self._channel_id = self._get_id(channel_name)
        logging.debug("Channel id: " + self._channel_id)

        self.__trigger_map = TriggerMap()
        self.__trigger_map.add_trigger(self.receive_message, TriggerSignal.MESSAGE)

        self.__event_sub = EventSub(bot_id=self._bot_id, channel_id=self._channel_id,
                                    subscription_types=["channel.chat.message"], auth_server=self.__auth, trigger_map=self.__trigger_map)

        self.__thread = ThreadWithExc(target=self.__run_event_server)
        self.__thread.start()


    def _get_id(self, user_name: str) -> str:
        data = self.__auth.get_request(endpoint=TwitchEndpoint.USER_ID + user_name)
        return data['data'][0]['id']

    def send_message(self, message: str, reply_message_id: str = None):
        data = {
            "broadcaster_id": self._channel_id,
            "sender_id": self._bot_id,
            "message": message,
        }
        if reply_message_id:
            data["reply_parent_message_id"] = reply_message_id

        add_data = self.__auth.post_request(endpoint=TwitchEndpoint.SEND_MESSAGE, data=data)['data'][0]

        if not add_data["is_sent"]:
            logging.warning(f"Message not sent: {add_data['drop_reason']}")
            drop_code = add_data["drop_reason"]["code"]
            drop_message = add_data["drop_reason"]["message"]
            raise TwitchMessageNotSentWarning(f"{drop_code}: {drop_message}")

    def __run_event_server(self):
        try:
            logging.info("Run Event Server!")
            self.__event_sub.run_forever()
        except KillThreadException:
            logging.info("Stop Event Server")


    def stop_event_server(self):
        self.__event_sub.keep_running = False

    def receive_message(self, message):
        logging.info("Message receive")
        logging.debug(message)