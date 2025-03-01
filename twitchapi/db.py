import sqlite3
import os
from threading import Lock
from typing import Callable
import logging
from twitchapi.utils import ThreadWithExc
from twitchapi.exception import KillThreadException
import time


class DataBaseTemplate:
    MESSAGE = ("INSERT INTO message (id, user, message, date, cheer, emote) values('<id>','<user>','<message>',"
               "DATETIME('<date>', 'subsec'),<cheer>,<emote>)"),
    THREAD = ("INSERT INTO message (id, user, message, date, cheer, emote) values('<id>','<user>','<message>',"
              "DATETIME('<date>', 'subsec'),<parent_id>,<thread_id>,<cheer>,<emote>)")

    @staticmethod
    def apply_param(script: str, **kwargs):
        for param in kwargs:
            marker = f"<{param}>"
            if marker not in script:
                raise AttributeError(f"{param} is not supported by the endpoint {script}")
            script = script.replace(marker, kwargs[param])
        return script


class DataBaseManager:

    class __InitDataBaseTemplate:
        MESSAGE = """CREATE TABLE message (
                         id VARCHAR(100) PRIMARY KEY NOT NULL,
                         user VARCHAR(100) NOT NULL,
                         message TEXT NOT NULL,
                         parent_id VARCHAR(100),
                         thread_id VARCHAR(100),
                         cheer BOOLEAN NOT NULL,
                         date DATE NOT NULL,
                         emote BOOLEAN NOT NULL
                     )"""

    def __init__(self, db_path: str, start_thread=False):
        if not os.path.exists(db_path):
            self.__initialize_db(db_path)

        self.__db = sqlite3.connect(database=db_path, check_same_thread=False)
        self.__cursor = self.__db.cursor()
        self.__lock = Lock()
        self.__start_thread = start_thread

        if self.__start_thread:
            self.__thread = ThreadWithExc(target=self.__auto_commit)
            self.__thread.start()

    def __initialize_db(self, db_path: str):
        db = sqlite3.connect(database=db_path, check_same_thread=False)
        cursor = db.cursor()

        cursor.execute(self.__InitDataBaseTemplate.MESSAGE)
        db.commit()
        db.close()

    def execute_script(self, script:str, **kwargs):
        script = DataBaseTemplate.apply_param(script, **kwargs)
        logging.debug(script)
        self.__lock_method(self.__cursor.execute, script)

    def commit(self):
        logging.info("Try commiting ingested data...")
        self.__lock_method(self.__db.commit)
        logging.info("Data commited!")

    def close(self):
        if self.__start_thread:
            self.__thread.raise_exc(KillThreadException)
            self.__thread.join()

        if self.__lock.locked():
            self.__lock.release()

        logging.info("Commit last change on database")
        self.commit()
        self.__db.close()
        logging.info("Stop data ingestion")

    def __lock_method(self, callback: Callable, *args, **kwargs):
        self.__lock.acquire()
        data = callback(*args, **kwargs)
        self.__lock.release()
        return data

    def __auto_commit(self):
        try:
            while True:
                self.commit()
                time.sleep(10)
        except KillThreadException:
            logging.info("Stop auto commit thread!")
