import logging
import time

from twitchapi.twitchcom import TwitchEndpoint, TriggerSignal, TwitchSubscriptionModel, TwitchRightType
from twitchapi.exception import TwitchMessageNotSentWarning, KillThreadException
from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT, ACCESS_TOKEN_FILE
from twitchapi.utils import ThreadWithExc, TriggerMap
from twitchapi.eventsub import EventSub


class ChatBot:
    """
    Class to drive the chatbot. It contains all the methods for requesting the Twitch api and receiving notifications,
    and is responsible for launching authentication with Twitch.
    """
    # Default right required for all methods making requests to the Twitch API
    DEFAULT_RIGHT = [TwitchRightType.MODERATOR_READ_FOLLOWERS, TwitchRightType.USER_WRITE_CHAT,
                     TwitchRightType.MODERATOR_READ_CHATTERS, TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS,
                     TwitchRightType.MODERATOR_MANAGE_BANNED_USERS]

    def __init__(self, client_id: str, client_secret: str, bot_name: str, channel_name: str,
                 subscriptions: list[str] = None, token_file_path: str = ACCESS_TOKEN_FILE,
                 redirect_uri_auth: str = REDIRECT_URI_AUTH, timeout=DEFAULT_TIMEOUT, right: list[str] = None,
                 channel_point_subscription: list[str] = None, store_in_db: bool = False):
        """
        :param client_id: id of the client twitch application
        :param client_secret: secret of the client twitch application
        :param bot_name: name of the bot twitch user account
        :param channel_name: name of the broadcaster channel
        :param subscriptions: list of subscription the bot will receive notification
        :param redirect_uri_auth: Uri of the callback server
        :param timeout
        :param right: right list of the bot (if none the right will be established with the subscription list)
        :param channel_point_subscription: list of channel reward name the bot will be subscribed to
        :param store_in_db: True if you want to store all the stream into a SQLite database
        """
        self._client_id = client_id
        self.__client_secret = client_secret

        self.__subscription = subscriptions

        # Default rights are estimated by the maximum number of rights required for each event subscription.
        if not right and self.__subscription:
            self.__right = TwitchSubscriptionModel("", "").which_right(self.__subscription)
        elif right:
            self.__right = right
        else:
            self.__right = []

        self.__right += self.DEFAULT_RIGHT

        # Performs authentication
        self.__auth = AuthServer()
        self.__auth.authentication(client_id=client_id, client_secret=client_secret, scope=self.__right,
                                   token_file_path=token_file_path, timeout=timeout, redirect_uri=redirect_uri_auth)

        self._bot_id = self._get_id(bot_name)
        logging.debug("Bot id: " + self._bot_id)
        self._channel_id = self._get_id(channel_name)
        logging.debug("Channel id: " + self._channel_id)

        # If the chatbot needs to be connected to the EventSub Twitch WebSocket
        if subscriptions:
            # Link each Twitch event notification (follow, sub, raid, ...) to a chatbot method that can be overridden as
            # needed
            self.__trigger_map = TriggerMap()
            self.__trigger_map.add_trigger(self.receive_message, TriggerSignal.MESSAGE)
            self.__trigger_map.add_trigger(self.new_follow, TriggerSignal.FOLLOW)
            self.__trigger_map.add_trigger(self.new_ban, TriggerSignal.BAN)
            self.__trigger_map.add_trigger(self.new_unban, TriggerSignal.UNBAN)
            self.__trigger_map.add_trigger(self.new_subscribe, TriggerSignal.SUBSCRIBE)
            self.__trigger_map.add_trigger(self.end_subscribe, TriggerSignal.SUBSCRIBE_END)
            self.__trigger_map.add_trigger(self.new_subgift, TriggerSignal.SUBGIFT)
            self.__trigger_map.add_trigger(self.new_resub, TriggerSignal.RESUB_MESSAGE)
            self.__trigger_map.add_trigger(self.raid_on_caster, TriggerSignal.RAID)
            self.__trigger_map.add_trigger(self.raid_someone, TriggerSignal.RAID_SOMEONE)
            self.__trigger_map.add_trigger(self.channel_reward, TriggerSignal.CHANNEL_POINT_ACTION)
            self.__trigger_map.add_trigger(self.channel_cheer, TriggerSignal.CHANNEL_CHEER)
            self.__trigger_map.add_trigger(self.new_poll, TriggerSignal.POLL_BEGIN)
            self.__trigger_map.add_trigger(self.poll_end, TriggerSignal.POLL_END)
            self.__trigger_map.add_trigger(self.new_prediction, TriggerSignal.PREDICTION_BEGIN)
            self.__trigger_map.add_trigger(self.prediction_lock, TriggerSignal.PREDICTION_LOCK)
            self.__trigger_map.add_trigger(self.prediction_end, TriggerSignal.PREDICTION_END)
            self.__trigger_map.add_trigger(self.new_vip, TriggerSignal.VIP_ADD)
            self.__trigger_map.add_trigger(self.remove_vip, TriggerSignal.VIP_REMOVE)
            self.__trigger_map.add_trigger(self.stream_online, TriggerSignal.STREAM_ONLINE)
            self.__trigger_map.add_trigger(self.stream_offline, TriggerSignal.STREAM_OFFLINE)
            self.__trigger_map.add_trigger(self.new_bits, TriggerSignal.BITS)

            self.__event_sub = EventSub(bot_id=self._bot_id, channel_id=self._channel_id,
                                        subscription_types=self.__subscription, auth_server=self.__auth,
                                        trigger_map=self.__trigger_map,
                                        channel_point_subscription=channel_point_subscription, store_in_db=store_in_db)

            self.__thread = ThreadWithExc(target=self.__run_event_server)
            self.__thread.start()

    def _get_id(self, user_name: str) -> str:
        """
        Get the Twitch ID of a user
        :param user_name: name of a user
        :return: the id of the user
        """
        data = self.__auth.get_request(endpoint=TwitchEndpoint.apply_param(TwitchEndpoint.USER_ID, user_id=user_name))
        return data['data'][0]['id']

    def send_message(self, message: str, reply_message_id: str = None):
        """
        Send a message to the chat of the broadcaster channel
        :param message: message to send
        :param reply_message_id: if the message is a reply of another, id of the source message
        """
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
        """
        Start the EventSub websocket on the host to catch EventSub notification from Twitch
        """
        try:
            while True:
                logging.info("Run Event Server!")
                self.__event_sub.run_forever()
        except KillThreadException:
            logging.info("Stop Event Server")

    def stop_event_server(self):
        """
        Stop the EvenSub websocket on the host
        """
        self.__event_sub.keep_running = False

    def get_subscriber(self):
        """
        Get all subscriber of the broadcaster channel
        """
        endpoint = TwitchEndpoint.apply_param(TwitchEndpoint.GET_SUBSCRIBERS, channel_id=self._channel_id)
        return self.__browse_all(self.__auth.get_request, endpoint)

    def get_follower(self):
        """
        Get all follower of the broadcaster channel
        """
        endpoint = TwitchEndpoint.apply_param(TwitchEndpoint.GET_FOLLOWERS, channel_id=self._channel_id)
        return self.__browse_all(self.__auth.get_request, endpoint)

    def get_ban_user(self):
        """
        Get all user banned from the broadcaster channel
        """
        endpoint = TwitchEndpoint.apply_param(TwitchEndpoint.GET_BAN, channel_id=self._channel_id)
        return self.__browse_all(self.__auth.get_request, endpoint)

    def get_connected_users(self):
        """
        Get all user connected to the stream of the broadcaster
        """
        endpoint = TwitchEndpoint.apply_param(TwitchEndpoint.GET_CHATTERS, channel_id=self._channel_id,
                                              moderator_id=self._bot_id)
        return self.__browse_all(self.__auth.get_request, endpoint)

    def __browse_all(self, callback, endpoint: str):
        """
        If the query returns only part of the information, returns all the information related to a query
        :param callback: request function
        :param endpoint: Request url
        :return:
        """
        # For more information: https://dev.twitch.tv/docs/api/guide/#pagination
        if not "?" in endpoint:
            endpoint += "?first=100"
        else:
            endpoint += "&first=100"
        out = callback(endpoint)
        data = out["data"]
        while out["pagination"]:
            cursor = out["pagination"]["cursor"]
            out = callback(endpoint + f"&after={cursor}")
            data += out["data"]
        return data

    def ban_user(self, user_name: str, reason: str, duration: int = None):
        """
        Ban a user
        :param user_name: name of the user
        :param reason: reason of the ban
        :param duration: if the ban is a timeout, time of the ban
        """
        data = {"user_id": self._get_id(user_name), "reason": reason}
        if duration:
            data["duration"] = duration
        self.__auth.post_request(TwitchEndpoint.apply_param(TwitchEndpoint.BAN, channel_id=self._channel_id,
                                                            moderator_id=self._bot_id), data=data)

    def receive_message(self, id: str, user_id: str, user_name: str, text: str, cheer: bool, emote: bool,
                        thread_id: str,
                        parent_id: str):
        """
        Triggered callback when the EventSub websocket receive a message notification
        :param id: id of the message
        :param user_name: name of the user that send the message
        :param text: text of the message
        :param cheer: True if the message contains cheer
        :param emote: True if the message contains emote
        :param thread_id: if the message is in a thread, id of the thread
        :param parent_id: if the message is in a thread, id of the source message replied to by this message
        """
        pass

    def channel_reward(self, user_id: str, user_name: str, reward_name: str):
        """
        Triggered callback when the EventSub websocket receive a channel reward notification
        :param user_name: name of the user that claims the reward
        :param reward_name: name of the reward claimed
        """
        pass

    def channel_cheer(self, user_name: str, message: str, nb_bits: int, is_anonymous: bool):
        """
        Triggered callback when the EventSub websocket receive a cheer notification
        :param user_name: name of the user that send the cheer (null if is_anonymous is True)
        :param message: message of the user
        :param nb_bits: number of bits send with the cheer
        :param is_anonymous: True if the user is anonymous
        """
        pass

    def new_follow(self, user_id: str, user_name: str):
        """
        Triggered callback when the EventSub websocket receive a follow notification
        :param user_name: name of the user that follows the broadcaster channel
        """
        pass

    def new_subscribe(self, user_id: str, user_name: str, tier: str, is_gift: bool):
        """
        Triggered callback when the EventSub websocket receive a subscribe notification
        :param user_name: name of the user that subscribes to the broadcaster channel
        :param tier: tier level of the subscription ("1000" = tier 1, "2000" = tier 2, "3000" : tier 3)
        :param is_gift: if the subscription is a gift
        """
        pass

    def end_subscribe(self, user_id:str, user_name:str):
        """
                Triggered callback when the EventSub websocket receive an end subscription notification
                :param user_name: name of the user that subscribes to the broadcaster channel
                """
        pass

    def new_subgift(self, user_name: str, tier: str, total: int, total_gift_sub: int, is_anonymous: bool):
        """
        Triggered callback when the EventSub websocket receive a subscription gift notification
        :param user_name: name of the user that send the subscription gift (null if is_anonymous is True)
        :param tier: tier level of the subscription ("1000" = tier 1, "2000" = tier 2, "3000" : tier 3)
        :param total: number of subscriptions offered
        :param total_gift_sub: number of subscriptions offered since forever (null if is_anonymous is True)
        :param is_anonymous: True if the user is anonymous
        :return:
        """
        pass

    def new_resub(self, user_name: str, tier: str, streak: int, total: int, duration: int, message: str):
        """
        Triggered callback when the EventSub websocket receive a resubscription notification
        :param user_name: name of the user that renew his subscription to the channel broadcaster
        :param tier: tier level of the subscription ("1000" = tier 1, "2000" = tier 2, "3000" : tier 3)
        :param streak: number of consecutive months of subscription
        :param total: total number of subscriptions since forever
        :param duration: duration of subscription
        :param message: message linked to the subscription
        """
        pass

    def raid_on_caster(self, source: str, nb_viewers: int):
        """
        Triggered callback when the EventSub websocket receive a raid notification and the broadcaster is raided
        :param source: channel name that raid the broadcaster
        :param nb_viewers: number of viewers of the raid
        """
        pass

    def raid_someone(self, dest: str, nb_viewers: int):
        """
        Triggered callback when the EventSub websocket receive a raid notification and the broadcaster raid someone
        :param dest: channel name raid by the broadcaster
        :param nb_viewers: number of viewers of the raid
        """
        pass

    def new_poll(self, title: str, choices: dict, bits_settings: dict, channel_point_settings: dict, start_date: str,
                 end_date: str):
        """
        Triggered callback when the EventSub websocket receive a new poll notification
        :param title: title of the poll
        :param choices: choices available of the poll
        :param bits_settings: settings link to the bits if the bits are available for the poll
        :param channel_point_settings: settings link to the channel point if the channel points are available for the
        poll
        :param start_date: poll start date
        :param end_date: poll end date
        """
        pass

    def poll_end(self, title: str, choices: dict, status: str):
        """
        Triggered callback when the EventSub websocket receive a poll end notification
        :param title: title of the poll
        :param choices: result of the poll choices
        :param status: status of the poll ("completed", "archived" or "terminated")
        """
        pass

    def new_prediction(self, title: str, choices: dict, start_date: str, lock_date: str):
        """
        Triggered callback when the EventSub websocket receive a new prediction notification
        :param title: title of the prediction
        :param choices: choices available for the prediction
        :param start_date: prediction start date
        :param lock_date: date where the prediction choices are locked
        """
        pass

    def prediction_lock(self, title: str, result: dict):
        """
        Triggered callback when the EventSub websocket receive a prediction locked notification
        :param title: title of the prediction
        :param result: result of the prediction
        """
        pass

    def prediction_end(self, title: str, result: dict, winning_pred: str):
        """
        Triggered callback when the EventSub websocket receive a prediction end notification
        :param title: title of the prediction
        :param result: result of the prediction
        :param winning_pred: prediction choice that wins the prediction
        """
        pass

    def new_ban(self, user_id:str, user_name: str, moderator_name: str, reason: str, start_ban: str, end_ban: str, permanent: bool):
        """
        Triggered callback when the EventSub websocket receive a new ban notification
        :param user_name: name of banned user
        :param moderator_name: name of the moderator who banned the user
        :param reason: reason of the ban
        :param start_ban: ban start date
        :param end_ban: if the ban is not permanent, ban end date
        :param permanent: True if the ban is permanent
        """
        pass

    def new_unban(self, user_id:str, user_name:str):
        """
        Triggered callback when the EventSub websocket receive a new unban notification
        :param user_name: name of banned user
        """
        pass

    def new_vip(self, user_name: str):
        """
        Triggered callback when the EventSub websocket receive a new vip notification
        :param user_name: name of user who has been promoted to vip
        """
        pass

    def remove_vip(self, user_name: str):
        """
        Triggered callback when the EventSub websocket receive a removed vip notification
        :param user_name: name of user who has lost vip status
        """
        pass

    def stream_online(self, type: str, start_time: str):
        """
        Triggered callback when the EventSub websocket receive a stream online notification
        :param type: type of the stream ("live", "playlist", "watch_party", "premiere" or "rerun")
        :param start_time: stream start date
        """
        pass

    def stream_offline(self):
        """
        Triggered callback when the EventSub websocket receive a stream offline notification
        """
        pass

    def new_bits(self, user_name: str, bits: int, type: str, power_up: str, message: str):
        """
        Triggered callback when the EventSub websocket receive a bits notification
        :param user_name: name of the user that sends bits
        :param bits: number of bits send
        :param type: possible value: "message_effect", "celebration" or "gigantify_an_emote"
        :param power_up: data of the power up, if a power up is used
        :param message: if a message is sent with the bits, text of the message
        """
        pass
