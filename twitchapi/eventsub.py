import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Any
from xml.sax import parse

from websocket import WebSocketApp

from twitchapi.auth import AuthServer
from twitchapi.utils import TwitchEndpoint, ThreadWithExc, TriggerMap, TriggerSignal, TwitchSubscriptionModel, \
    TwitchSubscriptionType
from twitchapi.exception import KillThreadException, TwitchEventSubError, TwitchMessageNotSentWarning
import json
import os
from threading import Lock


class EventSub(WebSocketApp):

    def __init__(self, bot_id: str, channel_id: str, subscription_types: list[str], auth_server: AuthServer,
                 trigger_map: TriggerMap = None):
        super().__init__(url=TwitchEndpoint.TWITCH_WEBSOCKET_URL, on_message=self.on_message, on_open=self.on_open,
                         on_close=self.on_close, on_error=self.on_error)

        self.__session_id = None
        self.__auth = auth_server
        self._bot_id = bot_id
        self._channel_id = channel_id
        self._subscription_types = subscription_types

        self.__tsm = TwitchSubscriptionModel(self._channel_id, self._bot_id)

        self.__db = sqlite3.connect(database=os.path.dirname(__file__) + "/database/TwitchDB", check_same_thread=False)
        self.__cursor = self.__db.cursor()

        self.__lock_db = Lock()

        self.__thread = ThreadWithExc(target=self.__execute_script_db)
        self.__thread.start()

        self.__trigger_map = trigger_map

    def on_message(self, ws, message):
        logging.debug("Message received:" + message)
        data = json.loads(message)

        metadata = data["metadata"]
        payload = data["payload"]

        message_type = metadata["message_type"]
        msg_timestamp = metadata["message_timestamp"][:-4]

        match message_type:
            case "session_welcome":
                logging.info("Receive session_welcome message")
                self.__session_id = payload["session"]["id"]
                self.__subscription()

            case "notification":
                logging.info("Receive notification message")
                subscription_type = payload["subscription"]["type"]

                match subscription_type:

                    case TwitchSubscriptionType.MESSAGE:
                        logging.info("Process a message")
                        self.__process_message(payload=payload, date=msg_timestamp)

                    case TwitchSubscriptionType.CHANNEL_POINT_ACTION:
                        logging.info("Process a channel point redeem")
                        self.__process_channel_point_action(payload=payload)

                    case TwitchSubscriptionType.FOLLOW:
                        logging.info("Process a follow")
                        self.__process_follow(payload=payload)

                    case TwitchSubscriptionType.BAN:
                        logging.info("Process a ban")
                        self.__process_ban(payload=payload)

                    case TwitchSubscriptionType.SUBSCRIBE:
                        logging.info("Process a subscribe")
                        self.__process_subscribe(payload=payload)

                    case TwitchSubscriptionType.SUBGIFT:
                        logging.info("Process a subgitf")
                        self.__process_subgift(payload=payload)

                    case TwitchSubscriptionType.RESUB_MESSAGE:
                        logging.info("Process a resub message")
                        self.__process_resub_message(payload=payload)

                    case TwitchSubscriptionType.RAID:
                        if payload["event"]["to_broadcaster_user_id"] == self._channel_id:
                            logging.info("Process a incoming raid")
                            self.__process_raid(payload=payload)
                        else:
                            logging.info("Process a raid")
                            self.__process_raid_someone(payload=payload)

                    case TwitchSubscriptionType.CHANNEL_POINT_ACTION:
                        logging.info("Process a channel action point")
                        self.__process_channel_point_action(payload=payload)

                    case TwitchSubscriptionType.POLL_BEGIN:
                        logging.info("Process a poll begin")
                        self.__process_poll_begin(payload=payload)

                    case TwitchSubscriptionType.POLL_END:
                        logging.info("Process a poll end")
                        self.__process_poll_end(payload=payload)

                    case TwitchSubscriptionType.PREDICTION_BEGIN:
                        logging.info("Process a prediction begin")
                        self.__process_prediction_begin(payload=payload)

                    case TwitchSubscriptionType.PREDICTION_LOCK:
                        logging.info("Process a prediction lock")
                        self.__process_prediction_lock(payload=payload)

                    case TwitchSubscriptionType.PREDICTION_END:
                        logging.info("Process a prediction end")
                        self.__process_prediction_end(payload=payload)

                    case TwitchSubscriptionType.VIP_ADD:
                        logging.info("Process a VIP added")
                        self.__process_vip_add(payload=payload)

                    case TwitchSubscriptionType.STREAM_ONLINE:
                        logging.info("Process a stream online notification")
                        self.__process_stream_online(payload=payload)

                    case TwitchSubscriptionType.STREAM_OFFLINE:
                        logging.info("Process a stream offline notification")
                        self.__process_stream_offline()

                    case TwitchSubscriptionType.BITS:
                        logging.info("Process bits received")
                        self.__process_bits(payload=payload)


    def on_error(self, ws, message):
        logging.error(message)

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("Close websocket")
        self.__thread.raise_exc(KillThreadException)
        self.__thread.join()

    def on_open(self, ws):
        logging.info(f"Connect to {TwitchEndpoint.TWITCH_WEBSOCKET_URL}")

    def __subscription(self):
        for subscription in self._subscription_types:
            logging.info(f"Subscription for {subscription}")
            s_data = self.__tsm.get_subscribe_data(subscription)["payload"]
            data = {
                "transport": {
                    "method": "websocket",
                    "session_id": self.__session_id
                }
            }
            data.update(s_data)
            self.__auth.post_request(TwitchEndpoint.EVENTSUB_SUBSCRIPTION, data=data)

    def __db__insert__message(self, id: str, user: str, message: str, date: str, parent_id: str = None,
                              thread_id: str = None, cheer: bool = False, emote: bool = False):
        date_str = f"DATETIME('{date}', 'subsec')"
        if parent_id:
            if not thread_id:
                raise ValueError(f"Missing thread_id value for parent_id {thread_id}")
            script = f"""INSERT INTO message (id, user, message, date, parent_id, thread_id, cheer, emote)
                        values({id},{user},{message},{date_str},{parent_id},{thread_id},{cheer},{emote})"""
        else:
            script = f"""INSERT INTO message (id, user, message, date, cheer, emote)
                        values('{id}','{user}','{message}',{date_str},{cheer},{emote})"""
        logging.info("Insert message data in database")
        logging.debug(script)
        try:
            self.__lock_method(self.__cursor.execute, self.__lock_db, script)
            logging.info('Data ingested')
        except Exception as e:
            logging.error(str(e.__class__) + ": " + str(e))

    def __execute_script_db(self):
        try:
            while True:
                logging.info("Try commiting ingested data...")
                self.__lock_method(self.__db.commit, self.__lock_db)
                logging.info("Data commited!")
                time.sleep(10)
        except KillThreadException:
            if self.__lock_db.locked():
                self.__lock_db.release()
            logging.info("Commit last change on database")
            self.__lock_method(self.__db.commit, self.__lock_db)
            logging.info("Stop data ingestion")

    def __lock_method(self, callback: Callable, lock: Lock, *args, **kwargs):
        lock.acquire()
        data = callback(*args, **kwargs)
        lock.release()
        return data

    def get_message(self, start_id: str = None):
        script = f"""SELECT * from message
                              WHERE date > (SELECT date FROM message WHERE id='{start_id}')"""
        recs = self.__lock_method(self.__cursor.execute, self.__lock_db, script)
        return recs

    def __process_message(self, payload: dict[str, Any], date):
        event = payload["event"]
        id = event['message_id']
        user_name = event["chatter_user_login"]
        message = event["message"]["text"]
        cheer = True if event["cheer"] else False
        emote = True if len(event["message"]["fragments"]) > 1 else False
        thread_id = event["reply"]['thread_message_id'] if event["reply"] else None
        parent_id = event["reply"]['parent_message_id'] if event["reply"] else None
        last_message = {"id": id, "user": user_name, "text": message, "cheer": cheer, "emote": emote,
                        "thread_id": thread_id, "parent_id": parent_id}
        self.__trigger_map.trigger(TriggerSignal.MESSAGE, param=last_message)
        self.__db__insert__message(id=id, user=user_name, message=message, date=date,
                                   parent_id=parent_id, thread_id=thread_id, cheer=cheer, emote=emote)


    def __process_channel_point_action(self, payload: dict):
        event = payload["event"]
        user = event["user_name"]
        reward_name = event["reward"]["title"]
        self.__trigger_map.trigger(TriggerSignal.CHANNEL_POINT_ACTION,
                                   param={"user_name": user, "reward_name": reward_name})

    def __process_follow(self, payload: dict):
        user = payload["event"]["user_name"]
        self.__trigger_map.trigger(TriggerSignal.FOLLOW, param={"user": user})

    def __process_subscribe(self, payload: dict):
        event = payload["event"]
        user = event["user_name"]
        tier = event["tier"]
        is_gift = event["is_gift"]
        self.__trigger_map.trigger(TriggerSignal.SUBSCRIBE, param={"user_name": user, "tier": tier,
                                                                   "is_gift": is_gift})

    def __process_subgift(self, payload: dict):
        event = payload["event"]
        gifter = event["user_name"]
        total = event["total"]
        tier = event["tier"]
        total_gift_sub = event["cumulative_total"]
        self.__trigger_map.trigger(TriggerSignal.SUBGIFT, param={"user_name": gifter, "tier": tier, "total": total,
                                                                 "total_gift_sub": total_gift_sub})

    def __process_resub_message(self, payload: dict):
        event = payload["event"]
        user = event["user_name"]
        tier = event["tier"]
        streak = event["streak_months"]
        total = event["cumulative_months"]
        duration = event["duration_months"]
        message = event["message"]["text"]
        self.__trigger_map.trigger(TriggerSignal.RESUB_MESSAGE, param={"user_name": user, "tier": tier,
                                                                       "streak": streak, "total": total,
                                                                       "duration": duration, "message": message})

    def __process_raid(self, payload: dict):
        event = payload["event"]
        user_source = event["from_broadcaster_user_name"]
        nb_viewers = event["viewers"]
        self.__trigger_map.trigger(TriggerSignal.RAID, param={"from": user_source, "nb_viewers": nb_viewers})

    def __process_raid_someone(self, payload: dict):
        event = payload["event"]
        user_dest = event["to_broadcaster_user_name"]
        nb_viewers = event["viewers"]
        self.__trigger_map.trigger(TriggerSignal.RAID_SOMEONE, param={"dest": user_dest, "nb_viewers": nb_viewers})

    def __process_poll_begin(self, payload: dict):
        event = payload["event"]
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

    def __process_poll_end(self, payload: dict):
        event = payload["event"]
        poll_title = event["title"]
        choices = event["choices"]
        status = event["status"]
        self.__trigger_map.trigger(TriggerSignal.POLL_END, param={"title": poll_title, "choices": choices,
                                                                  "status": status})

    def __process_prediction_begin(self, payload: dict):
        event = payload["event"]
        pred_title = event["title"]
        choices = event["outcomes"]
        start = event["started_at"]
        lock = event["locks_at"]
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_BEGIN, param={"title": pred_title, "choices": choices,
                                                                          "start_date": start, "lock_date": lock})

    def __process_prediction_lock(self, payload: dict):
        event = payload["event"]
        pred_title = event["title"]
        result = event["outcomes"]
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_BEGIN, param={"title": pred_title, "result": result})

    def __process_prediction_end(self, payload: dict):
        event = payload["event"]
        pred_title = event["title"]
        result = event["outcomes"]
        winning = None
        for r in result:
            if r["id"] == event["winning_outcome_id"]:
                winning = r["title"]
                break
        if not winning:
            raise TwitchEventSubError(f"There's no winning prediction for {pred_title}")
        self.__trigger_map.trigger(TriggerSignal.PREDICTION_BEGIN, param={"title": pred_title, "result": result,
                                                                          "winning_pred": winning})

    def __process_ban(self, payload: dict):
        event = payload["event"]
        user = event["user_name"]
        reason = event["reason"]
        ban_date = event["banned_at"]
        end_ban = event["ends_at"]
        permanent = event["is_permanent"]
        self.__trigger_map.trigger(TriggerSignal.BAN, param={"user_name": user, "reason": reason, "start_ban": ban_date,
                                                             "end_ban": end_ban, "permanent": permanent})

    def __process_vip_add(self, payload:dict):
        event = payload["event"]
        user = event["user_name"]
        self.__trigger_map.trigger(TriggerSignal.VIP_ADD, param={"user_name": user})

    def __process_stream_online(self, payload:dict):
        event = payload["event"]
        type = event["type"]
        start = event["started_at"]
        self.__trigger_map.trigger(TriggerSignal.STREAM_ONLINE, param={"type": type, "start_time": start})

    def __process_stream_offline(self):
        self.__trigger_map.trigger(TriggerSignal.STREAM_OFFLINE)

    def __process_bits(self, payload:dict):
        event = payload["event"]
        user = event["user_name"]
        bits_number = event["bits"]
        type = event["type"]
        power_up = event["power_up"]
        message = event["message"]["text"]
        self.__trigger_map.trigger(TriggerSignal.BITS, param={"user_name": user, "bits": bits_number, "type": type,
                                                              "power_up": power_up, "message": message})