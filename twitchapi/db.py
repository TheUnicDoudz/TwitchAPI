from threading import Lock
import sqlite3

from typing import Callable
import logging
import time
import os

from twitchapi.exception import KillThreadException
from twitchapi.utils import ThreadWithExc


class DataBaseTemplate:
    """
    Template for request made on the SQLite database
    """
    MESSAGE = """INSERT INTO message (id, user, user_id, message, date, cheer, emote) 
                 VALUES('<id>', '<user>', '<user_id>', '<message>', DATETIME('<date>', 'subsec') ,<cheer>, <emote>)"""

    THREAD = """INSERT INTO message 
                VALUES('<id>', '<user>', '<user_id>', '<message>', DATETIME('<date>', 'subsec'), '<parent_id>', 
                       '<thread_id>', <cheer>, <emote>)"""

    CHANNEL_POINT_ACTION = """INSERT INTO reward 
                              VALUES('<id>', '<user>', '<user_id>', '<reward_name>', '<reward_id>', '<reward_prompt>',
                                     '<status>', DATETIME('<date>', 'subsec'), DATETIME('<redeem_date>', 'subsec'), 
                                     <cost>)"""

    CHANNEL_CHEER = """INSERT INTO cheer
                       VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), <nb_bits>, <anonymous>)"""

    FOLLOW = """INSERT INTO follow 
                VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), 
                       DATETIME('<follow_date>', 'subsec'))"""

    SUBSCRIBE = """INSERT INTO subscribe (id, user, user_id, date, tier, is_gift, duration)
                   VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), '<tier>', <is_gift>, 1)
                   """

    RESUB = """INSERT INTO subscribe
               VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), '<message>', '<tier>', <streak>, 
                      FALSE, <duration>, <total>)"""

    SUBGIFT = """INSERT INTO subgift
                 VALUES('<id>', <user>, <user_id>, DATETIME('<date>', 'subsec'), '<tier>', <total>, <total_gift>, 
                        <is_anonymous>)"""

    RAID = """INSERT INTO raid
              VALUES('<id>', '<user_source>', '<user_source_id>', '<user_dest>', '<user_dest_id>', 
                     DATETIME('<date>', 'subsec'), <nb_viewer>)"""

    POLL = """INSERT INTO poll
              VALUES('<id>', '<title>', <bits_enable>, <bits_amount_per_vote>, <channel_point_enable>, 
                     <channel_point_amount_per_vote>, DATETIME('<start_date>', 'subsec'), 
                     DATETIME('<end_date>', 'subsec'), '<status>')"""

    POLL_CHOICES = """INSERT INTO poll_choices
                      VALUES('<id>', '<title>', <bits_votes>, <channel_points_votes>, <votes>, '<poll_id>')"""

    PREDICTION = """INSERT INTO prediction
                    VALUES('<id>', '<title>', '<winning_outcome>', '<winning_outcome_id>', 
                           DATETIME('<start_date>', 'subsec'), DATETIME('<end_date>', 'subsec'), '<status>')"""

    PREDICTION_CHOICES = """INSERT INTO prediction_choices
                            VALUES('<id>', '<title>', <nb_users>, <channel_points>, '<prediction_id>')"""

    BAN = """INSERT INTO ban
             VALUES('<id>', '<user>', '<user_id>', '<moderator>', '<moderator_id>', '<reason>', 
                    DATETIME('<start_ban>', 'subsec'), DATETIME('<end_ban>', 'subsec'), <is_permanent>)"""

    ADD_VIP = """INSERT INTO vip
             VALUES('<user_id>', '<user>', DATETIME('<date>', 'subsec'))"""

    REMOVE_VIP = """DELETE FROM vip WHERE user_id='<user_id>'"""

    BITS = """INSERT INTO bits
              VALUES('<id>', '<user_id>', '<user>', '<type>', <nb_bits>, <power_up>, <message>, 
                     DATETIME('<date>', 'subsec'))"""

    @staticmethod
    def apply_param(script: str, **kwargs):
        for param in kwargs:
            marker = f"<{param}>"
            if marker not in script:
                raise AttributeError(f"{param} is not supported by the endpoint {script}")
            script = script.replace(marker, str(kwargs[param]))
        return script


class DataBaseManager:
    """
    Class to manage the SQLite database
    """
    class __InitDataBaseTemplate:
        """
        Template to initialise the SQLite database
        """
        MESSAGE = """CREATE TABLE message (
                         id VARCHAR(36) PRIMARY KEY NOT NULL,
                         user VARCHAR(100) NOT NULL,
                         user_id VARCHAR(100) NOT NULL,
                         message TEXT NOT NULL,
                         parent_id VARCHAR(36),
                         thread_id VARCHAR(36),
                         cheer BOOLEAN NOT NULL,
                         date DATE NOT NULL,
                         emote BOOLEAN NOT NULL
                     )"""

        CHANNEL_POINT_ACTION = """CREATE TABLE reward (
                                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                                      user VARCHAR(100) NOT NULL,
                                      user_id VARCHAR(100) NOT NULL,
                                      reward_name VARCHAR(45) NOT NULL,
                                      reward_id VARCHAR(36) NOT NULL,
                                      reward_prompt TEXT,
                                      status VARCHAR(20),
                                      date DATE NOT NULL,
                                      redeem_date DATE NOT NULL,
                                      cost INT NOT NULL
                                  )"""

        CHANNEL_CHEER = """CREATE TABLE cheer (
                               id VARCHAR(36) PRIMARY KEY NOT NULL,
                               user VARCHAR(100),
                               user_id VARCHAR(100),
                               date DATE NOT NULL,
                               nb_bits INT NOT NULL,
                               anonymous BOOLEAN NOT NULL
                           )"""

        FOLLOW = """CREATE TABLE follow (
                        id VARCHAR(36) PRIMARY KEY NOT NULL,
                        user VARCHAR(100) NOT NULL,
                        user_id VARCHAR(100) NOT NULL,
                        date DATE NOT NULL,
                        follow_date DATE NOT NULL
                    )"""

        SUBSCRIBE = """CREATE TABLE subscribe (
                           id VARCHAR(36) PRIMARY KEY NOT NULL,
                           user VARCHAR(100),
                           user_id VARCHAR(100),
                           date DATE NOT NULL,
                           message TEXT,
                           tier VARCHAR(4) NOT NULL,
                           streak INT,
                           is_gift BOOLEAN NOT NULL,
                           duration INT NOT NULL,
                           total INT
                       )"""

        SUBGIFT = """CREATE TABLE subgift (
                         id VARCHAR(36) PRIMARY KEY NOT NULL,
                         user VARCHAR(100) NOT NULL,
                         user_id VARCHAR(100) NOT NULL,
                         date DATE NOT NULL,
                         tier VARCHAR(4) NOT NULL,
                         total INT NOT NULL,
                         total_gift INT,
                         is_anonymous BOOL NOT NULL
                     )"""

        RAID = """CREATE TABLE raid (
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      user_source VARCHAR(100) NOT NULL,
                      user_source_id VARCHAR(100) NOT NULL,
                      user_dest VARCHAR(100) NOT NULL,
                      user_dest_id VARCHAR(100) NOT NULL,
                      date DATE NOT NULL,
                      nb_viewer INT NOT NULL
                  )"""

        POLL = """CREATE TABLE poll (
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      title TEXT NOT NULL,
                      bits_enable BOOLEAN NOT NULL,
                      bits_amount_per_vote INT,
                      channel_point_enable BOOLEAN NOT NULL,
                      channel_point_amount_per_vote INT,
                      start_date DATE NOT NULL,
                      end_date DATE NOT NULL,
                      status VARCHAR(20) NOT NULL
                  )"""

        POLL_CHOICES = """CREATE TABLE poll_choices (
                              id VARCHAR(36) PRIMARY KEY NOT NULL,
                              title TEXT NOT NULL,
                              bits_votes INT,
                              channel_points_votes INT,
                              votes INT NOT NULL,
                              poll_id VARCHAR(36),
                              FOREIGN KEY(poll_id) REFERENCES poll(id)
                          )"""

        PREDICTION = """CREATE TABLE prediction (
                            id VARCHAR(36) PRIMARY KEY NOT NULL,
                            title TEXT NOT NULL,
                            winning_outcome TEXT,
                            winning_outcome_id VARCHAR(36),
                            start_date DATE NOT NULL,
                            end_date DATE NOT NULL,
                            status VARCHAR(20) NOT NULL
                        )"""

        PREDICTION_CHOICES = """CREATE TABLE prediction_choices (
                                    id VARCHAR(36) PRIMARY KEY NOT NULL,
                                    title TEXT NOT NULL,
                                    nb_users INT NOT NULL,
                                    channel_points INT NOT NULL,
                                    prediction_id VARCHAR(36),
                                    FOREIGN KEY(prediction_id) REFERENCES prediction(id)
                                )"""

        BAN = """CREATE TABLE ban (
                     id VARCHAR(36) PRIMARY KEY NOT NULL,
                     user VARCHAR(100) NOT NULL,
                     user_id VARCHAR(100) NOT NULL,
                     moderator VARCHAR(100) NOT NULL,
                     moderator_id VARCHAR(100) NOT NULL,
                     reason TEXT NOT NULL,
                     start_ban DATE NOT NULL,
                     end_ban DATE,
                     is_permanent BOOLEAN NOT NULL
                 )"""

        VIP = """CREATE TABLE vip (
                     user_id VARCHAR(100) PRIMARY KEY NOT NULL,
                     user VARCHAR(100) NOT NULL,
                     date DATE NOT NULL
                 )"""

        BITS = """CREATE TABLE bits(
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      user_id VARCHAR(100) NOT NULL,
                      user VARCHAR(100) NOT NULL,
                      type VARCHAR(10) NOT NULL,
                      nb_bits INT NOT NULL,
                      power_up VARCHAR(20),
                      message TEXT,
                      date DATE NOT NULL
                  )"""

    def __init__(self, db_path: str, start_thread=False):
        """
        :param db_path: path of the database
        :param start_thread: True if the user wants the database to be enriched automatically every 10 seconds
        """
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
        """
        Initialize the SQLite database
        :param db_path: path of the database
        """
        db = sqlite3.connect(database=db_path, check_same_thread=False)
        cursor = db.cursor()

        cursor.execute(self.__InitDataBaseTemplate.MESSAGE)
        cursor.execute(self.__InitDataBaseTemplate.CHANNEL_POINT_ACTION)
        cursor.execute(self.__InitDataBaseTemplate.FOLLOW)
        cursor.execute(self.__InitDataBaseTemplate.SUBSCRIBE)
        cursor.execute(self.__InitDataBaseTemplate.SUBGIFT)
        cursor.execute(self.__InitDataBaseTemplate.RAID)
        cursor.execute(self.__InitDataBaseTemplate.POLL)
        cursor.execute(self.__InitDataBaseTemplate.POLL_CHOICES)
        cursor.execute(self.__InitDataBaseTemplate.PREDICTION)
        cursor.execute(self.__InitDataBaseTemplate.PREDICTION_CHOICES)
        cursor.execute(self.__InitDataBaseTemplate.BAN)
        cursor.execute(self.__InitDataBaseTemplate.VIP)
        cursor.execute(self.__InitDataBaseTemplate.BITS)
        db.commit()
        db.close()

    @staticmethod
    def __lock_method(callback: Callable):
        """
        Decorator to prevent database queries from colliding
        :param callback: function that will be encapsulated by the semaphore
        """

        def wrapper(self, *args, **kwargs):
            self.__lock.acquire()
            data = callback(self, *args, **kwargs)
            self.__lock.release()
            return data

        return wrapper

    @__lock_method
    def execute_script(self, script: str, **kwargs):
        """
        Execute a SQL script on the database
        :param script: script template
        :param kwargs: information to applied on the template script
        """
        try:
            script = DataBaseTemplate.apply_param(script, **kwargs)
            logging.debug(script)
            self.__cursor.execute(script)
            logging.info('Data ingested')
        except Exception as e:
            logging.error(str(e.__class__.__name__) + ": " + str(e))
            raise e

    @__lock_method
    def commit(self):
        """
        Commit the modification on the database
        """
        logging.info("Try commiting ingested data...")
        self.__db.commit()
        logging.info("Data commited!")

    def close(self):
        """
        Close the connection with the database
        """
        if self.__start_thread:
            self.__thread.raise_exc(KillThreadException)
            self.__thread.join()

        if self.__lock.locked():
            self.__lock.release()

        logging.info("Commit last change on database")
        self.commit()
        self.__db.close()
        logging.info("Stop data ingestion")



    def __auto_commit(self):
        """
        Commit automatically modification of the database every 10 seconds
        """
        try:
            while True:
                self.commit()
                time.sleep(10)
        except KillThreadException:
            logging.info("Stop auto commit thread!")
