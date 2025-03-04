import logging

from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT
from twitchapi.exception import TwitchMessageNotSentWarning, KillThreadException
from twitchapi.eventsub import EventSub
from twitchapi.twitchcom import TwitchEndpoint, TriggerSignal, TwitchSubscriptionModel
from twitchapi.utils import ThreadWithExc, TriggerMap

class ChatBot:
    DEFAULT_RIGHT = ["moderator:read:followers", "user:write:chat", "moderator:read:chatters",
                     "moderator:read:chatters"]

    def __init__(self, client_id: str, client_secret: str, bot_name: str, channel_name: str, subscriptions: list[str],
                 redirect_uri_auth: str = REDIRECT_URI_AUTH, timeout=DEFAULT_TIMEOUT, right: list[str] = None,
                 channel_point_subscription: list[str] = None):
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__subscription = subscriptions
        if not right:
            self.__right = TwitchSubscriptionModel("", "").which_right(self.__subscription)
        else:
            self.__right = right

        self.__right += self.DEFAULT_RIGHT

        self.__auth = AuthServer()
        self.__auth.authentication(client_id=client_id, client_secret=client_secret, scope=self.__right,
                                   timeout=timeout, redirect_uri=redirect_uri_auth)

        self._bot_id = self._get_id(bot_name)
        logging.debug("Bot id: " + self._bot_id)
        self._channel_id = self._get_id(channel_name)
        logging.debug("Channel id: " + self._channel_id)

        self.__trigger_map = TriggerMap()
        self.__trigger_map.add_trigger(self.receive_message, TriggerSignal.MESSAGE)
        self.__trigger_map.add_trigger(self.new_follow, TriggerSignal.FOLLOW)
        self.__trigger_map.add_trigger(self.new_ban, TriggerSignal.BAN)
        self.__trigger_map.add_trigger(self.new_subscribe, TriggerSignal.SUBSCRIBE)
        self.__trigger_map.add_trigger(self.new_subgift, TriggerSignal.SUBGIFT)
        self.__trigger_map.add_trigger(self.new_resub, TriggerSignal.RESUB_MESSAGE)
        self.__trigger_map.add_trigger(self.raid_on_caster, TriggerSignal.RAID)
        self.__trigger_map.add_trigger(self.raid_someone, TriggerSignal.RAID_SOMEONE)
        self.__trigger_map.add_trigger(self.channel_reward, TriggerSignal.CHANNEL_POINT_ACTION)
        self.__trigger_map.add_trigger(self.new_poll, TriggerSignal.POLL_BEGIN)
        self.__trigger_map.add_trigger(self.poll_end, TriggerSignal.POLL_END)
        self.__trigger_map.add_trigger(self.new_prediction, TriggerSignal.PREDICTION_BEGIN)
        self.__trigger_map.add_trigger(self.prediction_lock, TriggerSignal.PREDICTION_LOCK)
        self.__trigger_map.add_trigger(self.prediction_end, TriggerSignal.PREDICTION_END)
        self.__trigger_map.add_trigger(self.new_vip, TriggerSignal.VIP_ADD)
        self.__trigger_map.add_trigger(self.stream_online, TriggerSignal.STREAM_ONLINE)
        self.__trigger_map.add_trigger(self.stream_offline, TriggerSignal.STREAM_OFFLINE)
        self.__trigger_map.add_trigger(self.new_bits, TriggerSignal.BITS)

        self.__event_sub = EventSub(bot_id=self._bot_id, channel_id=self._channel_id,
                                    subscription_types=self.__subscription, auth_server=self.__auth,
                                    trigger_map=self.__trigger_map,
                                    channel_point_subscription=channel_point_subscription)

        self.__thread = ThreadWithExc(target=self.__run_event_server)
        self.__thread.start()

    def _get_id(self, user_name: str) -> str:
        data = self.__auth.get_request(endpoint=TwitchEndpoint.apply_param(TwitchEndpoint.USER_ID, user_id=user_name))
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

    def get_follower(self):
        return self.__auth.get_request(TwitchEndpoint.apply_param(TwitchEndpoint.GET_FOLLOWERS,
                                                                  user_id=self._channel_id))["data"]

    def get_connected_users(self):
        return self.__auth.get_request(TwitchEndpoint.apply_param(TwitchEndpoint.GET_CHATTERS,
                                                                  channel_id=self._channel_id,
                                                                  moderator_id=self._bot_id))["data"]

    def ban_user(self, user_id: str, reason: str, duration: int = None):
        data = {"user_id": user_id, "reason": reason}
        if duration:
            data["duration"] = duration
        self.__auth.post_request(TwitchEndpoint.apply_param(TwitchEndpoint.BAN, channel_id=self._channel_id,
                                                            moderator_id=self._bot_id), data=data)

    def receive_message(self, id: str, user_name: str, text: str, cheer: bool, emote: bool, thread_id: str,
                        parent_id: str):
        pass

    def channel_reward(self, user_name: str, reward_name: str):
        pass

    def new_follow(self, user_name: str):
        pass

    def new_subscribe(self, user_name: str, tier: str, is_gift: bool):
        pass

    def new_subgift(self, user_name: str, tier: str, total: int, total_gift_sub: int, is_anonymous: bool):
        pass

    def new_resub(self, user_name: str, tier: str, streak: int, total: int, duration: int, message: str):
        pass

    def raid_on_caster(self, source: str, nb_viewers: int):
        pass

    def raid_someone(self, dest: str, nb_viewers: int):
        pass

    def new_poll(self, title: str, choices: dict, bits_settings: dict, channel_point_settings: dict, start_date: str,
                 end_date: str):
        pass

    def poll_end(self, title: str, choices: dict, status: str):
        pass

    def new_prediction(self, title: str, choices: dict, start_date: str, lock_date: str):
        pass

    def prediction_lock(self, title: str, result: dict):
        pass

    def prediction_end(self, title: str, result: dict, winning_pred: str):
        pass

    def new_ban(self, user_name: str, reason: str, start_ban: str, end_date: str, permanent: bool):
        pass

    def new_vip(self, user_name: str):
        pass

    def stream_online(self, type: str, start_time: str):
        pass

    def stream_offline(self):
        pass

    def new_bits(self, user_name: str, bits: int, type: str, power_up: str, message: str):
        pass
