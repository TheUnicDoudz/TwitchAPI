"""
Database management module for storing Twitch events in SQLite.

This module provides classes for managing SQLite database operations,
including table creation, data insertion, and automated commits.
All Twitch events can be stored for later analysis and reporting.

Author: TheUnicDoudz
"""

from threading import Lock
import sqlite3
import logging
import time
import os
from typing import Callable, Optional, Dict
from contextlib import contextmanager

from twitchapi.exception import KillThreadException
from twitchapi.utils import ThreadWithExc

logger = logging.getLogger(__name__)


def format_text(text: str) -> str:
    """
    Format text for safe database insertion by removing problematic characters.

    Args:
        text: Input text to format

    Returns:
        Formatted text safe for database insertion
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""

    # Replace quotes that could cause SQL injection issues
    # and other problematic characters
    return text.replace('"', ' ').replace("'", ' ').replace('\n', ' ').replace('\r', ' ')


class DataBaseTemplate:
    """
    Template class containing SQL query templates for all Twitch event types.

    This class provides parameterized SQL templates that can be safely
    populated with event data using the apply_param method.
    """

    # Chat message insertion template
    MESSAGE = """INSERT INTO message (id, user, user_id, message, date, cheer, emote) 
                 VALUES('<id>', '<user>', '<user_id>', '<message>', DATETIME('<date>', 'subsec'), <cheer>, <emote>)"""

    # Threaded message insertion template
    THREAD = """INSERT INTO message 
                VALUES('<id>', '<user>', '<user_id>', '<message>', DATETIME('<date>', 'subsec'), '<parent_id>', 
                       '<thread_id>', <cheer>, <emote>)"""

    # Channel point reward redemption template
    CHANNEL_POINT_ACTION = """INSERT INTO reward 
                              VALUES('<id>', '<user>', '<user_id>', '<reward_name>', '<reward_id>', '<reward_prompt>',
                                     '<status>', DATETIME('<date>', 'subsec'), DATETIME('<redeem_date>', 'subsec'), 
                                     <cost>)"""

    # Bits/cheer event template
    CHANNEL_CHEER = """INSERT INTO cheer
                       VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), <nb_bits>, <anonymous>)"""

    # New follower template
    FOLLOW = """INSERT INTO follow 
                VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), 
                       DATETIME('<follow_date>', 'subsec'))"""

    # New subscription template
    SUBSCRIBE = """INSERT INTO subscribe (id, user, user_id, date, tier, is_gift, duration)
                   VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), '<tier>', <is_gift>, 1)"""

    # Resubscription template
    RESUB = """INSERT INTO subscribe
               VALUES('<id>', '<user>', '<user_id>', DATETIME('<date>', 'subsec'), '<message>', '<tier>', <streak>, 
                      FALSE, <duration>, <total>)"""

    # Gift subscription template
    SUBGIFT = """INSERT INTO subgift
                 VALUES('<id>', <user>, <user_id>, DATETIME('<date>', 'subsec'), '<tier>', <total>, <total_gift>, 
                        <is_anonymous>)"""

    # Raid event template
    RAID = """INSERT INTO raid
              VALUES('<id>', '<user_source>', '<user_source_id>', '<user_dest>', '<user_dest_id>', 
                     DATETIME('<date>', 'subsec'), <nb_viewer>)"""

    # Poll creation template
    POLL = """INSERT INTO poll
              VALUES('<id>', '<title>', <bits_enable>, <bits_amount_per_vote>, <channel_point_enable>, 
                     <channel_point_amount_per_vote>, DATETIME('<start_date>', 'subsec'), 
                     DATETIME('<end_date>', 'subsec'), '<status>')"""

    # Poll choices template
    POLL_CHOICES = """INSERT INTO poll_choices
                      VALUES('<id>', '<title>', <bits_votes>, <channel_points_votes>, <votes>, '<poll_id>')"""

    # Prediction creation template
    PREDICTION = """INSERT INTO prediction
                    VALUES('<id>', '<title>', '<winning_outcome>', '<winning_outcome_id>', 
                           DATETIME('<start_date>', 'subsec'), DATETIME('<end_date>', 'subsec'), '<status>')"""

    # Prediction choices template
    PREDICTION_CHOICES = """INSERT INTO prediction_choices
                            VALUES('<id>', '<title>', <nb_users>, <channel_points>, '<prediction_id>')"""

    # Ban event template
    BAN = """INSERT INTO ban
             VALUES('<id>', '<user>', '<user_id>', '<moderator>', '<moderator_id>', '<reason>', 
                    DATETIME('<start_ban>', 'subsec'), DATETIME('<end_ban>', 'subsec'), <is_permanent>)"""

    # VIP addition template
    ADD_VIP = """INSERT INTO vip
                 VALUES('<user_id>', '<user>', DATETIME('<date>', 'subsec'))"""

    # VIP removal template
    REMOVE_VIP = """DELETE FROM vip WHERE user_id='<user_id>'"""

    # Bits usage template (for special effects)
    BITS = """INSERT INTO bits
              VALUES('<id>', '<user_id>', '<user>', '<type>', <nb_bits>, <power_up>, <message>, 
                     DATETIME('<date>', 'subsec'))"""

    @staticmethod
    def apply_param(script: str, **kwargs) -> str:
        """
        Apply parameters to a SQL template safely.

        Args:
            script: SQL template string with <parameter> placeholders
            **kwargs: Parameters to substitute in the template

        Returns:
            SQL string with parameters applied

        Raises:
            AttributeError: If a required parameter is missing
            ValueError: If parameter values are invalid
        """
        if not isinstance(script, str):
            raise ValueError("script must be a string")

        result_script = script

        for param, value in kwargs.items():
            marker = f"<{param}>"

            if marker not in result_script:
                raise AttributeError(f"Parameter '{param}' is not supported by the template")

            # Format value appropriately for SQL
            if value is None:
                formatted_value = "NULL"
            elif isinstance(value, bool):
                formatted_value = "TRUE" if value else "FALSE"
            elif isinstance(value, (int, float)):
                formatted_value = str(value)
            else:
                # String values - already quoted in templates
                formatted_value = format_text(str(value))

            result_script = result_script.replace(marker, formatted_value)

        # Check for any remaining unreplaced parameters
        import re
        remaining_params = re.findall(r'<(\w+)>', result_script)
        if remaining_params:
            raise AttributeError(f"Missing required parameters: {remaining_params}")

        return result_script


class DataBaseManager:
    """
    SQLite database manager for storing and retrieving Twitch event data.

    This class handles database connection management, table creation,
    data insertion, and automatic commits. It provides thread-safe operations
    and can optionally run an auto-commit thread.
    """

    class __InitDataBaseTemplate:
        """
        Database table creation templates.

        These templates define the schema for all Twitch event tables.
        """

        MESSAGE = """CREATE TABLE message (
                         id VARCHAR(36) PRIMARY KEY NOT NULL,
                         user VARCHAR(100) NOT NULL,
                         user_id VARCHAR(100) NOT NULL,
                         message TEXT NOT NULL,
                         parent_id VARCHAR(36),
                         thread_id VARCHAR(36),
                         cheer BOOLEAN NOT NULL,
                         date DATETIME NOT NULL,
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
                                      date DATETIME NOT NULL,
                                      redeem_date DATETIME NOT NULL,
                                      cost INT NOT NULL
                                  )"""

        CHANNEL_CHEER = """CREATE TABLE cheer (
                               id VARCHAR(36) PRIMARY KEY NOT NULL,
                               user VARCHAR(100),
                               user_id VARCHAR(100),
                               date DATETIME NOT NULL,
                               nb_bits INT NOT NULL,
                               anonymous BOOLEAN NOT NULL
                           )"""

        FOLLOW = """CREATE TABLE follow (
                        id VARCHAR(36) PRIMARY KEY NOT NULL,
                        user VARCHAR(100) NOT NULL,
                        user_id VARCHAR(100) NOT NULL,
                        date DATETIME NOT NULL,
                        follow_date DATETIME NOT NULL
                    )"""

        SUBSCRIBE = """CREATE TABLE subscribe (
                           id VARCHAR(36) PRIMARY KEY NOT NULL,
                           user VARCHAR(100),
                           user_id VARCHAR(100),
                           date DATETIME NOT NULL,
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
                         date DATETIME NOT NULL,
                         tier VARCHAR(4) NOT NULL,
                         total INT NOT NULL,
                         total_gift INT,
                         is_anonymous BOOLEAN NOT NULL
                     )"""

        RAID = """CREATE TABLE raid (
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      user_source VARCHAR(100) NOT NULL,
                      user_source_id VARCHAR(100) NOT NULL,
                      user_dest VARCHAR(100) NOT NULL,
                      user_dest_id VARCHAR(100) NOT NULL,
                      date DATETIME NOT NULL,
                      nb_viewer INT NOT NULL
                  )"""

        POLL = """CREATE TABLE poll (
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      title TEXT NOT NULL,
                      bits_enable BOOLEAN NOT NULL,
                      bits_amount_per_vote INT,
                      channel_point_enable BOOLEAN NOT NULL,
                      channel_point_amount_per_vote INT,
                      start_date DATETIME NOT NULL,
                      end_date DATETIME NOT NULL,
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
                            start_date DATETIME NOT NULL,
                            end_date DATETIME NOT NULL,
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
                     start_ban DATETIME NOT NULL,
                     end_ban DATETIME,
                     is_permanent BOOLEAN NOT NULL
                 )"""

        VIP = """CREATE TABLE vip (
                     user_id VARCHAR(100) PRIMARY KEY NOT NULL,
                     user VARCHAR(100) NOT NULL,
                     date DATETIME NOT NULL
                 )"""

        BITS = """CREATE TABLE bits(
                      id VARCHAR(36) PRIMARY KEY NOT NULL,
                      user_id VARCHAR(100) NOT NULL,
                      user VARCHAR(100) NOT NULL,
                      type VARCHAR(10) NOT NULL,
                      nb_bits INT NOT NULL,
                      power_up VARCHAR(20),
                      message TEXT,
                      date DATETIME NOT NULL
                  )"""

    def __init__(self, db_path: str, start_thread: bool = False):
        """
        Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
            start_thread: Whether to start auto-commit thread

        Raises:
            sqlite3.Error: If database initialization fails
            OSError: If database directory cannot be created
        """
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path must be a non-empty string")

        self.__db_path = db_path.strip()
        self.__start_thread = start_thread
        self.__db = None
        self.__cursor = None
        self.__lock = Lock()
        self.__thread = None
        self.__is_closed = False

        try:
            # Initialize database if it doesn't exist
            if not os.path.exists(self.__db_path):
                logger.info(f"Creating new database at {self.__db_path}")
                self.__initialize_db()

            # Open database connection
            self.__db = sqlite3.connect(
                database=self.__db_path,
                check_same_thread=False,
                timeout=30.0  # 30 second timeout for locks
            )
            self.__cursor = self.__db.cursor()

            # Enable foreign key constraints
            self.__cursor.execute("PRAGMA foreign_keys = ON")

            # Optimize database performance
            self.__cursor.execute("PRAGMA journal_mode = WAL")
            self.__cursor.execute("PRAGMA synchronous = NORMAL")

            logger.info(f"Database connection established: {self.__db_path}")

            # Start auto-commit thread if requested
            if self.__start_thread:
                self.__thread = ThreadWithExc(target=self.__auto_commit)
                self.__thread.daemon = True
                self.__thread.start()
                logger.info("Auto-commit thread started")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self.__cleanup_failed_init()
            raise

    def __initialize_db(self) -> None:
        """
        Initialize the database by creating all required tables.

        Raises:
            sqlite3.Error: If table creation fails
            OSError: If directory creation fails
        """
        try:
            # Create directory if it doesn't exist
            db_dir = os.path.dirname(self.__db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # Create database and tables
            db = sqlite3.connect(database=self.__db_path, check_same_thread=False)
            cursor = db.cursor()

            # Create all tables
            table_templates = [
                self.__InitDataBaseTemplate.MESSAGE,
                self.__InitDataBaseTemplate.CHANNEL_POINT_ACTION,
                self.__InitDataBaseTemplate.FOLLOW,
                self.__InitDataBaseTemplate.SUBSCRIBE,
                self.__InitDataBaseTemplate.SUBGIFT,
                self.__InitDataBaseTemplate.RAID,
                self.__InitDataBaseTemplate.POLL,
                self.__InitDataBaseTemplate.POLL_CHOICES,
                self.__InitDataBaseTemplate.PREDICTION,
                self.__InitDataBaseTemplate.PREDICTION_CHOICES,
                self.__InitDataBaseTemplate.BAN,
                self.__InitDataBaseTemplate.VIP,
                self.__InitDataBaseTemplate.BITS,
                self.__InitDataBaseTemplate.CHANNEL_CHEER
            ]

            for template in table_templates:
                cursor.execute(template)

            db.commit()
            db.close()
            logger.info("Database tables created successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def __cleanup_failed_init(self) -> None:
        """Clean up resources after failed initialization."""
        try:
            if self.__cursor:
                self.__cursor.close()
            if self.__db:
                self.__db.close()
        except:
            pass  # Ignore cleanup errors

    @staticmethod
    def __lock_method(callback: Callable) -> Callable:
        """
        Decorator to ensure thread-safe database operations.

        Args:
            callback: Function to wrap with lock

        Returns:
            Thread-safe wrapped function
        """

        def wrapper(self, *args, **kwargs):
            if self.__is_closed:
                raise RuntimeError("Database connection is closed")

            with self.__lock:
                try:
                    return callback(self, *args, **kwargs)
                except Exception as e:
                    logger.error(f"Database operation failed: {e}")
                    raise

        return wrapper

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Yields:
            Database cursor for transaction operations

        Example:
            with db_manager.transaction() as cursor:
                cursor.execute("INSERT INTO ...")
                cursor.execute("UPDATE ...")
        """
        if self.__is_closed:
            raise RuntimeError("Database connection is closed")

        with self.__lock:
            try:
                yield self.__cursor
                self.__db.commit()
                logger.debug("Transaction committed successfully")
            except Exception as e:
                self.__db.rollback()
                logger.error(f"Transaction rolled back due to error: {e}")
                raise

    @__lock_method
    def execute_script(self, script: str, **kwargs) -> None:
        """
        Execute a parameterized SQL script.

        Args:
            script: SQL template with parameter placeholders
            **kwargs: Parameters to substitute in the template

        Raises:
            sqlite3.Error: If SQL execution fails
            AttributeError: If required parameters are missing
        """
        try:
            formatted_script = DataBaseTemplate.apply_param(script, **kwargs)
            logger.debug(f"Executing: {formatted_script[:100]}...")

            self.__cursor.execute(formatted_script)
            logger.debug("Data inserted successfully")

        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            logger.debug(f"Failed script: {script}")
            raise

    @__lock_method
    def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """
        Execute a SELECT query and return results.

        Args:
            query: SQL SELECT query
            params: Query parameters (optional)

        Returns:
            List of query result tuples

        Raises:
            sqlite3.Error: If query execution fails
        """
        try:
            if params:
                self.__cursor.execute(query, params)
            else:
                self.__cursor.execute(query)

            results = self.__cursor.fetchall()
            logger.debug(f"Query returned {len(results)} rows")
            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    @__lock_method
    def commit(self) -> None:
        """
        Manually commit pending database changes.

        Raises:
            sqlite3.Error: If commit fails
        """
        try:
            logger.debug("Committing database changes...")
            self.__db.commit()
            logger.debug("Database changes committed successfully")
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            raise

    def get_stats(self) -> Dict[str, int]:
        """
        Get database statistics for all tables.

        Returns:
            Dictionary with table names and row counts
        """
        stats = {}
        tables = [
            'message', 'reward', 'follow', 'subscribe', 'subgift',
            'raid', 'poll', 'prediction', 'ban', 'vip', 'bits', 'cheer'
        ]

        for table in tables:
            try:
                results = self.execute_query(f"SELECT COUNT(*) FROM {table}")
                stats[table] = results[0][0] if results else 0
            except Exception as e:
                logger.warning(f"Failed to get stats for table {table}: {e}")
                stats[table] = -1

        return stats

    def close(self) -> None:
        """
        Close the database connection and clean up resources.

        This method ensures all pending changes are committed and
        properly shuts down the auto-commit thread if running.
        """
        if self.__is_closed:
            logger.warning("Database is already closed")
            return

        try:
            # Stop auto-commit thread
            if self.__thread and self.__thread.is_alive():
                logger.info("Stopping auto-commit thread...")
                self.__thread.raise_exc(KillThreadException)
                self.__thread.join(timeout=5.0)

                if self.__thread.is_alive():
                    logger.warning("Auto-commit thread did not stop gracefully")

            # Acquire lock to ensure no operations are in progress
            with self.__lock:
                # Commit any pending changes
                if self.__db:
                    logger.info("Committing final database changes...")
                    self.__db.commit()

                # Close cursor and connection
                if self.__cursor:
                    self.__cursor.close()
                    self.__cursor = None

                if self.__db:
                    self.__db.close()
                    self.__db = None

                self.__is_closed = True
                logger.info("Database connection closed successfully")

        except Exception as e:
            logger.error(f"Error closing database: {e}")
        finally:
            self.__is_closed = True

    def __auto_commit(self) -> None:
        """
        Auto-commit thread function that commits changes every 10 seconds.

        This runs in a separate daemon thread and automatically commits
        pending database changes at regular intervals.
        """
        try:
            logger.info("Auto-commit thread started")

            while not self.__is_closed:
                try:
                    time.sleep(10)  # Wait 10 seconds between commits
                    if not self.__is_closed:
                        self.commit()
                except KillThreadException:
                    logger.info("Auto-commit thread received stop signal")
                    break
                except Exception as e:
                    logger.error(f"Auto-commit error: {e}")
                    # Continue running despite errors

        except Exception as e:
            logger.error(f"Auto-commit thread crashed: {e}")
        finally:
            logger.info("Auto-commit thread stopped")

    def is_closed(self) -> bool:
        """
        Check if the database connection is closed.

        Returns:
            True if database is closed, False otherwise
        """
        return self.__is_closed

    def __del__(self) -> None:
        """Cleanup when object is destroyed."""
        try:
            self.close()
        except:
            pass  # Ignore errors during cleanup

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()