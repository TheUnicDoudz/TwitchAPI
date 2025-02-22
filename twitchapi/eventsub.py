import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from websocket import WebSocketApp

from twitchapi.auth import AuthServer
from twitchapi.utils import TwitchEndpoint, ThreadWithExc, TriggerMap, TriggerSignal
from twitchapi.exception import KillThreadException
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
                for subscription in self._subscription_types:
                    match subscription:
                        case "channel.chat.message":
                            logging.info("Subscription to get chat message")
                            condition = {"broadcaster_user_id": self._channel_id, "user_id": self._bot_id}
                            self.__subscription(subscription_type=subscription, condition=condition)

            case "notification":
                logging.info("Receive notification message")
                subscription_type = payload["subscription"]["type"]
                match subscription_type:
                    case "channel.chat.message":
                        logging.info("Process a message")
                        self.__process_message(payload=payload, date=msg_timestamp)

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
        self.__trigger_map.trigger(TriggerSignal.MESSAGE, message=last_message)
        self.__db__insert__message(id=id, user=user_name, message=message, date=date,
                                   parent_id=parent_id, thread_id=thread_id, cheer=cheer, emote=emote)

    def on_error(self, ws, message):
        logging.error(message)

    def on_close(self, ws, close_status_code, close_msg):
        logging.info("Close websocket")
        self.__thread.raise_exc(KillThreadException)
        self.__thread.join()

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