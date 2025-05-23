from typing import Any
import logging
import json
import os
import traceback

from websocket import WebSocketApp

from twitchapi.twitchcom import TwitchEndpoint, TriggerSignal, TwitchSubscriptionModel, \
    TwitchSubscriptionType
from twitchapi.exception import TwitchEventSubError, TwitchAuthorizationFailed
from twitchapi.db import DataBaseManager, DataBaseTemplate, format_text
from twitchapi.utils import TriggerMap
from twitchapi.auth import AuthServer

SOURCE_ROOT = os.path.dirname(__file__)
DEFAULT_DB_PATH = SOURCE_ROOT + "/database/TwitchDB.db"


class EventSub(WebSocketApp):
    """
    Class that creates a client websocket and links it with Twitch's websocket to receive event notifications
    """

    def __init__(self, bot_id: str, channel_id: str, subscription_types: list[str], auth_server: AuthServer,
                 trigger_map: TriggerMap = None, store_in_db: bool = False, db_path: str = DEFAULT_DB_PATH,
                 channel_point_subscription: list[str] = None):
        """
        :param bot_id: id of the client twitch application
        :param channel_id: id of the broadcaster channel
        :param subscription_types:
        :param auth_server: list of subscription the websocket will receive notification
        :param trigger_map: map of callback to trigger
        :param store_in_db: True if the user want to store all information from notification in the database
        :param db_path: path of the database
        :param channel_point_subscription: channel reward list the websocket will subscribe to
        """

        super().__init__(url=TwitchEndpoint.TWITCH_WEBSOCKET_URL, on_message=self.on_message, on_open=self.on_open,
                         on_close=self.on_close, on_error=self.on_error)

        self.__session_id = None
        self.__auth = auth_server
        self._bot_id = bot_id
        self._channel_id = channel_id
        self._subscription_types = subscription_types

        self.__tsm = TwitchSubscriptionModel(self._channel_id, self._bot_id)
        self.__channel_point_subscription = channel_point_subscription

        self.__store_in_db = store_in_db
        if self.__store_in_db:
            self.__dbmanager = DataBaseManager(db_path, start_thread=True)

        self.__trigger_map = trigger_map

    def on_message(self, ws, message):
        """
        Triggered when the websocket receive a message
        :param ws: websocket client
        :param message: message receive by the websocket
        """
        logging.debug("Message received:" + message)
        data = json.loads(message)

        metadata = data["metadata"]
        payload = data["payload"]

        message_type = metadata["message_type"]
        msg_timestamp = metadata["message_timestamp"][:-4]

        # The class expect 2 type of message:
        #   - session_welcome: message sent to initiate subscriptions to twitch events
        #   - notification: event notification message (type of event specified in the message “type” field)
        match message_type:
            case "session_welcome":
                # Initiate subscription to event
                logging.info("Receive session_welcome message")
                self.__session_id = payload["session"]["id"]
                self.__subscription()

            case "notification":
                # When an event is notified
                logging.info("Receive notification message")
                subscription_type = payload["subscription"]["type"]
                event = payload["event"]
                id = payload["subscription"]["id"]
                try:
                    match subscription_type:

                        case TwitchSubscriptionType.MESSAGE:
                            logging.info("Process a message")
                            self.__process_message(event=event, date=msg_timestamp)

                        case TwitchSubscriptionType.CHANNEL_POINT_ACTION:
                            logging.info("Process a channel point redeem")
                            self.__process_channel_point_action(event=event, date=msg_timestamp)

                        case TwitchSubscriptionType.FOLLOW:
                            logging.info("Process a follow")
                            self.__process_follow(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.BAN:
                            logging.info("Process a ban")
                            self.__process_ban(event=event, id=id)

                        case TwitchSubscriptionType.SUBSCRIBE:
                            logging.info("Process a subscribe")
                            self.__process_subscribe(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.SUBSCRIBE_END:
                            logging.info("Process an end subscription")
                            self.__process_end_subscribe(event=event)

                        case TwitchSubscriptionType.SUBGIFT:
                            logging.info("Process a subgitf")
                            self.__process_subgift(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.RESUB_MESSAGE:
                            logging.info("Process a resub message")
                            self.__process_resub_message(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.RAID:
                            if payload["event"]["to_broadcaster_user_id"] == self._channel_id:
                                logging.info("Process a incoming raid")
                                self.__process_raid(event=event, date=msg_timestamp, id=id)
                            else:
                                logging.info("Process a raid")
                                self.__process_raid_someone(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.CHANNEL_POINT_ACTION:
                            logging.info("Process a channel action point")
                            self.__process_channel_point_action(event=event, date=msg_timestamp)

                        case TwitchSubscriptionType.CHANNEL_CHEER:
                            logging.info("Process a cheer message")
                            self.__process_channel_cheer(event=event, date=msg_timestamp, id=id)

                        case TwitchSubscriptionType.POLL_BEGIN:
                            logging.info("Process a poll begin")
                            self.__process_poll_begin(event=event)

                        case TwitchSubscriptionType.POLL_END:
                            logging.info("Process a poll end")
                            self.__process_poll_end(event=event)

                        case TwitchSubscriptionType.PREDICTION_BEGIN:
                            logging.info("Process a prediction begin")
                            self.__process_prediction_begin(event=event)

                        case TwitchSubscriptionType.PREDICTION_LOCK:
                            logging.info("Process a prediction lock")
                            self.__process_prediction_lock(event=event)

                        case TwitchSubscriptionType.PREDICTION_END:
                            logging.info("Process a prediction end")
                            self.__process_prediction_end(event=event)

                        case TwitchSubscriptionType.VIP_ADD:
                            logging.info("Process a VIP added")
                            self.__process_vip_add(event=event, date=msg_timestamp)

                        case TwitchSubscriptionType.VIP_REMOVE:
                            logging.info("Process a VIP removed")
                            self.__process_vip_remove(event=event)

                        case TwitchSubscriptionType.STREAM_ONLINE:
                            logging.info("Process a stream online notification")
                            self.__process_stream_online(event=event)

                        case TwitchSubscriptionType.STREAM_OFFLINE:
                            logging.info("Process a stream offline notification")
                            self.__process_stream_offline()

                        case TwitchSubscriptionType.BITS:
                            logging.info("Process bits received")
                            self.__process_bits(event=event, date=msg_timestamp, id=id)

                except Exception as e:
                    logging.error(str(e.__class__.__name__) + ": " + str(e))
                    logging.error(traceback.format_exc())

    def on_error(self, ws, message):
        """
        Triggered when the websocket receive an error from the host
        :param ws: websocket client
        :param message: message receive by the websocket
        """
        logging.error(message)

    def on_close(self, ws, close_status_code, close_msg):
        """
        Triggered when the websocket close the connection with the host
        :param ws: websocket client
        :param close_status_code: closing status code
        :param close_msg: closure message
        """
        logging.info("Close websocket")
        if self.__store_in_db:
            self.__dbmanager.close()

    def on_open(self, ws):
        """
        Triggered when the websocket open the connection with the host
        :param ws: websocket client
        """
        logging.info(f"Connect to {TwitchEndpoint.TWITCH_WEBSOCKET_URL}")

    def __subscription(self):
        """
        Subscribes the websocket to all events listed in the _subscription_types list
        """
        for subscription in self._subscription_types:
            logging.info(f"Subscription for {subscription}")

            # Get the payload template for the subscription
            s_data = self.__tsm.get_subscribe_data(subscription)

            if s_data["streamer_only"] and self._bot_id != self._channel_id:
                raise TwitchAuthorizationFailed(
                    f"To subscribe to {subscription}, the account used for authentication has "
                    "to be the same as the broadcaster account!")

            s_data = s_data["payload"]

            data = {
                "transport": {
                    "method": "websocket",
                    "session_id": self.__session_id
                }
            }

            # If the user want to subscribe to specific channel reward event
            if subscription == TwitchSubscriptionType.CHANNEL_POINT_ACTION and self.__channel_point_subscription:
                custom_reward = self.__auth.get_request(TwitchEndpoint.apply_param(TwitchEndpoint.GET_CUSTOM_REWARD,
                                                                                   channel_id=self._channel_id))["data"]

                for reward_subscription in self.__channel_point_subscription:
                    logging.info(f"Subscription for {reward_subscription}")

                    subscription_title = reward_subscription.replace(" ", "").lower()
                    reward_id = None
                    for reward in custom_reward:
                        if reward["title"].replace(" ", "").lower() == subscription_title:
                            reward_id = reward["id"]
                            break

                    if not reward_id:
                        channel_name = self.__auth.get_request(
                            TwitchEndpoint.apply_param(TwitchEndpoint.CHANNEL_INFO, channel_id=self._channel_id))[
                            "data"][0]["broadcaster_name"]
                        raise KeyError(
                            f"Custom reward {reward_subscription} doesn't exist for the channel {channel_name}")

                    s_data["condition"]["reward_id"] = reward_id
                    data.update(s_data)
                    self.__auth.post_request(TwitchEndpoint.EVENTSUB_SUBSCRIPTION, data=data)
            else:
                data.update(s_data)
                self.__auth.post_request(TwitchEndpoint.EVENTSUB_SUBSCRIPTION, data=data)

    def __process_message(self, event: dict[str, Any], date: str):
        """
        When a message notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param date: timestamp of the notification
        """
        id = event['message_id']
        user_name = event["chatter_user_name"]
        user_id = event["chatter_user_id"]
        message = format_text(event["message"]["text"])
        cheer = True if event["cheer"] else False
        emote = True if len(event["message"]["fragments"]) > 1 else False
        thread_id = event["reply"]['thread_message_id'] if event["reply"] else None
        parent_id = event["reply"]['parent_message_id'] if event["reply"] else None
        last_message = {"id": id, "user_id":user_id, "user_name": user_name, "text": message, "cheer": cheer, "emote": emote,
                        "thread_id": thread_id, "parent_id": parent_id}

        self.__trigger_map.trigger(TriggerSignal.MESSAGE, param=last_message)

        if self.__store_in_db:
            logging.info("Insert message data in database")
            if parent_id:
                if not thread_id:
                    raise ValueError(f"Missing thread_id value for parent_id {thread_id}")
                self.__dbmanager.execute_script(DataBaseTemplate.THREAD, id=id, user=user_name, user_id=user_id,
                                                message=message, date=date, parent_id=parent_id, thread_id=thread_id,
                                                cheer=cheer, emote=emote)
            else:
                self.__dbmanager.execute_script(DataBaseTemplate.MESSAGE, id=id, user=user_name, user_id=user_id,
                                                message=message, date=date, cheer=cheer, emote=emote)

    def __process_channel_point_action(self, event: dict, date: str):
        """
        When a channel reward notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        user_id = event["user_id"]
        reward_name = event["reward"]["title"]
        self.__trigger_map.trigger(TriggerSignal.CHANNEL_POINT_ACTION,
                                   param={"user_name": user, "reward_name": reward_name, "user_id":user_id})

        if self.__store_in_db:
            id = event["id"]
            reward_id = event["reward"]["id"]
            reward_prompt = event["reward"]["prompt"]
            status = event["status"]
            redeem_date = event["redeemed_at"][:-4]
            reward_cost = event["reward"]["cost"]
            self.__dbmanager.execute_script(DataBaseTemplate.CHANNEL_POINT_ACTION, id=id, user=user, user_id=user_id,
                                            reward_name=reward_name, reward_id=reward_id, status=status, date=date,
                                            redeem_date=redeem_date, cost=reward_cost, reward_prompt=reward_prompt)

    def __process_channel_cheer(self, event: dict, id: str, date: str):
        """
        When a cheer notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        is_anonymous = event['is_anonymous']
        user_name = event["user_name"] if not is_anonymous else None
        message = event["message"]
        nb_bits = event["bits"]
        self.__trigger_map.trigger(TriggerSignal.CHANNEL_CHEER, param={"user_name": user_name, "message": message,
                                                                       "nb_bits": nb_bits, "is_anonymous": is_anonymous
                                                                       })

        if self.__store_in_db:
            user_id = event["user_id"] if not is_anonymous else None
            self.__dbmanager.execute_script(DataBaseTemplate.CHANNEL_CHEER, id=id, user=user_name, user_id=user_id,
                                            date=date, nb_bits=nb_bits, anonymous=str(is_anonymous).upper())

    def __process_follow(self, event: dict, id: str, date: str):
        """
        When a follow notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        user_id = event["user_id"]
        self.__trigger_map.trigger(TriggerSignal.FOLLOW, param={"user_name": user, "user_id": user_id})

        if self.__store_in_db:
            follow_date = event["followed_at"][:-4]
            self.__dbmanager.execute_script(DataBaseTemplate.FOLLOW, id=id, user=user, user_id=user_id, date=date,
                                            follow_date=follow_date)

    def __process_subscribe(self, event: dict, id: str, date: str):
        """
        When a subscription notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        tier = event["tier"]
        is_gift = event["is_gift"]
        user_id = event["user_id"]
        self.__trigger_map.trigger(TriggerSignal.SUBSCRIBE, param={"user_name": user, "tier": tier,
                                                                   "is_gift": is_gift, "user_id": user_id})

        if self.__store_in_db:
            self.__dbmanager.execute_script(DataBaseTemplate.SUBSCRIBE, id=id, user=user, user_id=user_id, date=date,
                                            tier=tier, is_gift=str(is_gift).upper())

    def __process_end_subscribe(self, event: dict):
        """
        When an end subscription notification is sent, extract all relevant information and trigger the associated
        callback
        :param event: event payload of the notification
        """
        user = event["user_name"]
        user_id = event["user_id"]
        self.__trigger_map.trigger(TriggerSignal.SUBSCRIBE_END, param={"user_name": user, "user_id": user_id})

    def __process_subgift(self, event: dict, id: str, date: str):
        """
        When a subscription gift notification is sent, extract all relevant information and trigger the associated
        callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        total = event["total"]
        tier = event["tier"]
        is_anonymous = event["is_anonymous"]
        gifter = event["user_name"] if not is_anonymous else "NULL"
        total_gift_sub = event["cumulative_total"] if not is_anonymous else "NULL"
        self.__trigger_map.trigger(TriggerSignal.SUBGIFT, param={"user_name": gifter, "tier": tier, "total": total,
                                                                 "total_gift_sub": total_gift_sub,
                                                                 "is_anonymous": is_anonymous})

        if self.__store_in_db:
            gifter_id = event["user_id"] if not is_anonymous else "NULL"
            gifter = f"'{gifter}'" if gifter != "NULL" else "NULL"
            gifter_id = f"'{gifter_id}'" if gifter_id != "NULL" else "NULL"
            self.__dbmanager.execute_script(DataBaseTemplate.SUBGIFT, id=id, user=gifter, user_id=gifter_id, date=date,
                                            tier=tier, total=total, total_gift=total_gift_sub,
                                            is_anonymous=str(is_anonymous).upper())

    def __process_resub_message(self, event: dict, id: str, date: str):
        """
        When a renewal subscription notification is sent, extract all relevant information and trigger the associated
        callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        tier = event["tier"]
        streak = event["streak_months"]
        total = event["cumulative_months"]
        duration = event["duration_months"]
        message = format_text(event["message"]["text"])
        self.__trigger_map.trigger(TriggerSignal.RESUB_MESSAGE, param={"user_name": user, "tier": tier,
                                                                       "streak": streak, "total": total,
                                                                       "duration": duration, "message": message})

        if self.__store_in_db:
            user_id = event["user_id"]
            self.__dbmanager.execute_script(DataBaseTemplate.RESUB, id=id, user=user, user_id=user_id, date=date,
                                            message=message, tier=tier, streak=streak, duration=duration, total=total)

    def __process_raid(self, event: dict, id: str, date: str):
        """
        When a raid notification is sent and the broadcaster is the one who be raided, extract all relevant information
        and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user_source = event["from_broadcaster_user_name"]
        nb_viewers = event["viewers"]
        self.__trigger_map.trigger(TriggerSignal.RAID, param={"source": user_source, "nb_viewers": nb_viewers})

        if self.__store_in_db:
            user_source_id = event["from_broadcaster_user_id"]
            user_dest = event["to_broadcaster_user_name"]
            self.__dbmanager.execute_script(DataBaseTemplate.RAID, id=id, user_source=user_source,
                                            user_source_id=user_source_id, user_dest=user_dest,
                                            user_dest_id=self._channel_id, date=date, nb_viewer=nb_viewers)

    def __process_raid_someone(self, event: dict, id: str, date: str):
        """
        When a raid notification is sent and the broadcaster is the one who raid, extract all relevant information and
        trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user_dest = event["to_broadcaster_user_name"]
        nb_viewers = event["viewers"]
        self.__trigger_map.trigger(TriggerSignal.RAID_SOMEONE, param={"dest": user_dest, "nb_viewers": nb_viewers})

        if self.__store_in_db:
            user_dest_id = event["from_broadcaster_user_id"]
            user_source = event["from_broadcaster_user_name"]
            self.__dbmanager.execute_script(DataBaseTemplate.RAID, id=id, user_source=user_source,
                                            user_source_id=self._channel_id, user_dest=user_dest,
                                            user_dest_id=user_dest_id, date=date, nb_viewer=nb_viewers)

    def __process_poll_begin(self, event: dict):
        """
        When a poll begin notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        poll_title = event["title"]
        choices = event["choices"]
        bits_settings = event["bits_voting"]
        channel_point_settings = event["channel_points_voting"]
        start = event["started_at"]
        end = event["ends_at"]
        self.__trigger_map.trigger(TriggerSignal.POLL_BEGIN, param={"title": poll_title, "choices": choices,
                                                                    "bits_settings": bits_settings,
                                                                    "channel_point_settings": channel_point_settings,
                                                                    "start_date": start, "end_date": end})

    def __process_poll_end(self, event: dict):
        """
        When a poll end notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        poll_title = event["title"]
        choices = event["choices"]
        status = event["status"]

        self.__trigger_map.trigger(TriggerSignal.POLL_END, param={"title": poll_title, "choices": choices,
                                                                  "status": status})

        if self.__store_in_db:
            id = event["id"]
            bits_enable = event["bits_voting"]["is_enabled"]
            bits_amount_per_vote = event["bits_voting"]["amount_per_vote"]
            channel_point_enable = event["channel_points_voting"]["is_enabled"]
            channel_point_amount_per_vote = event["channel_points_voting"]["amount_per_vote"]
            start_date = event["started_at"][:-4]
            end_date = event["ended_at"][:-4]
            self.__dbmanager.execute_script(DataBaseTemplate.POLL, id=id, title=poll_title, bits_enable=bits_enable,
                                            bits_amount_per_vote=bits_amount_per_vote, start_date=start_date,
                                            channel_point_enable=channel_point_enable, end_date=end_date,
                                            channel_point_amount_per_vote=channel_point_amount_per_vote, status=status)

            for c in choices:
                self.__dbmanager.execute_script(DataBaseTemplate.POLL_CHOICES, id=c["id"], title=c["title"],
                                                bits_votes=c["bits_votes"], votes=c["votes"], poll_id=id,
                                                channel_points_votes=c["channel_points_votes"])

    def __process_prediction_begin(self, event: dict):
        """
        When a prediction begin notification is sent, extract all relevant information and trigger the associated
        callback
        :param event: event payload of the notification
        """
        pred_title = event["title"]
        choices = event["outcomes"]
        start = event["started_at"]
        lock = event["locks_at"]
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_BEGIN, param={"title": pred_title, "choices": choices,
                                                                          "start_date": start, "lock_date": lock})

    def __process_prediction_lock(self, event: dict):
        """
        When a prediction lock notification is sent, extract all relevant information and trigger the associated
        callback
        :param event: event payload of the notification
        """
        pred_title = event["title"]
        result = event["outcomes"]
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_LOCK, param={"title": pred_title, "result": result})

    def __process_prediction_end(self, event: dict):
        """
        When a prediction end notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        pred_title = event["title"]
        result = event["outcomes"]
        winning = None

        # Find the winning prediction
        for r in result:
            if r["id"] == event["winning_outcome_id"]:
                winning = r["title"]
                break
        if not winning:
            raise TwitchEventSubError(f"There's no winning prediction for {pred_title}")
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_END, param={"title": pred_title, "result": result,
                                                                        "winning_pred": winning})

        if self.__store_in_db:
            id = event["id"]
            winning_id = event["winning_outcome_id"]
            start_date = event["started_at"][:-4]
            end_date = event["ended_at"][:-4]
            status = event["status"]
            self.__dbmanager.execute_script(DataBaseTemplate.PREDICTION, id=id, title=pred_title,
                                            winning_outcome=winning, winning_outcome_id=winning_id,
                                            start_date=start_date, end_date=end_date, status=status)

            for r in result:
                self.__dbmanager.execute_script(DataBaseTemplate.PREDICTION_CHOICES, id=r["id"], title=r["title"],
                                                nb_users=r["users"], channel_points=r["channel_points"],
                                                prediction_id=id)

    def __process_ban(self, event: dict, id: str):
        """
        When a ban notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        """
        user = event["user_name"]
        user_id = event["user_id"]
        reason = event["reason"]
        ban_date = event["banned_at"]
        end_ban = event["ends_at"]
        permanent = event["is_permanent"]
        moderator_name = event["moderator_user_name"]
        self.__trigger_map.trigger(TriggerSignal.BAN, param={"user_name": user, "moderator_name": moderator_name,
                                                             "reason": reason, "start_ban": ban_date,
                                                             "end_ban": end_ban, "permanent": permanent, "user_id": user_id})

        if self.__store_in_db:
            user_id = event["user_id"]
            moderator_id = event["moderator_user_id"]
            self.__dbmanager.execute_script(DataBaseTemplate.BAN, id=id, user=user, user_id=user_id,
                                            moderator=moderator_id, moderator_id=moderator_id, reason=reason,
                                            start_ban=ban_date, end_ban=end_ban, is_permanent=permanent)

    def __process_unban(self, event: dict):
        """
        When an unban notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        user = event["user_name"]
        user_id = event["user_id"]
        self.__trigger_map.trigger(TriggerSignal.UNBAN, param={"user_name": user, "user_id": user_id})

    def __process_vip_add(self, event: dict, date: str):
        """
        When a new vip notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        self.__trigger_map.trigger(TriggerSignal.VIP_ADD, param={"user_name": user})

        if self.__store_in_db:
            user_id = event["user_id"]
            self.__dbmanager.execute_script(DataBaseTemplate.ADD_VIP, user_id=user_id, user=user, date=date)

    def __process_vip_remove(self, event: dict):
        """
        When a removed vip notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        user = event["user_name"]
        self.__trigger_map.trigger(TriggerSignal.VIP_REMOVE, param={"user_name": user})

        if self.__store_in_db:
            user_id = event["user_id"]
            self.__dbmanager.execute_script(DataBaseTemplate.REMOVE_VIP, user_id=user_id)

    def __process_stream_online(self, event: dict):
        """
        When a stream online notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        """
        type = event["type"]
        start = event["started_at"]
        self.__trigger_map.trigger(TriggerSignal.STREAM_ONLINE, param={"type": type, "start_time": start})

    def __process_stream_offline(self):
        """
        When a stream offline notification is sent, extract all relevant information and trigger the associated callback
        """
        self.__trigger_map.trigger(TriggerSignal.STREAM_OFFLINE)

    def __process_bits(self, event: dict, id: str, date: str):
        """
        When a bits notification is sent, extract all relevant information and trigger the associated callback
        :param event: event payload of the notification
        :param id: id of the notification
        :param date: timestamp of the notification
        """
        user = event["user_name"]
        bits_number = event["bits"]
        type = event["type"]
        power_up = event["power_up"]
        message = format_text(event["message"]["text"])
        self.__trigger_map.trigger(TriggerSignal.BITS, param={"user_name": user, "bits": bits_number, "type": type,
                                                              "power_up": power_up, "message": message})

        if self.__store_in_db:
            user_id = event["user_id"]
            power_up = "NULL" if power_up else "'" + power_up + "'"
            message = "NULL" if message else "'" + message + "'"
            self.__dbmanager.execute_script(DataBaseTemplate.BITS, id=id, user_id=user_id, user=user, type=type,
                                            nb_bits=bits_number, power_up=power_up, message=message, date=date)
