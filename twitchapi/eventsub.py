"""
Enhanced EventSub module with rate limit handling for 429 errors.

This version includes automatic rate limit detection, backoff strategies,
and connection management to avoid "429 Too Many Requests" errors.
"""

import time
import random
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import os
import traceback

from websocket import WebSocketApp

from twitchapi.twitchcom import (
    TwitchEndpoint,
    TriggerSignal,
    TwitchSubscriptionModel,
    TwitchSubscriptionType
)
from twitchapi.exception import TwitchEventSubError, TwitchAuthorizationFailed
from twitchapi.db import DataBaseManager, format_text
from twitchapi.utils import TriggerMap
from twitchapi.auth import AuthServer

logger = logging.getLogger(__name__)

# Default database path
SOURCE_ROOT = os.path.dirname(__file__)
DEFAULT_DB_PATH = os.path.join(SOURCE_ROOT, "database", "TwitchDB.db")


class RateLimitAwareEventSub(WebSocketApp):
    """
    Enhanced EventSub WebSocket client with rate limit handling.

    This class extends WebSocketApp to handle Twitch's EventSub rate limits:
    - Maximum 3 WebSocket connections per app per 5 minutes
    - Maximum 10 subscription attempts per app per 10 seconds
    - Automatic backoff after 429 errors
    """

    def __init__(self,
                 bot_id: str,
                 channel_id: str,
                 subscription_types: List[str],
                 auth_server: AuthServer,
                 trigger_map: Optional[TriggerMap] = None,
                 store_in_db: bool = False,
                 db_path: str = DEFAULT_DB_PATH,
                 channel_point_subscription: Optional[List[str]] = None):
        """
        Initialize the rate-limit aware EventSub WebSocket client.
        """
        # Input validation
        if not bot_id or not isinstance(bot_id, str):
            raise ValueError("bot_id must be a non-empty string")
        if not channel_id or not isinstance(channel_id, str):
            raise ValueError("channel_id must be a non-empty string")
        if not subscription_types or not isinstance(subscription_types, list):
            raise ValueError("subscription_types must be a non-empty list")
        if not auth_server or not isinstance(auth_server, AuthServer):
            raise ValueError("auth_server must be a valid AuthServer instance")

        # Initialize WebSocket connection
        super().__init__(
            url=TwitchEndpoint.TWITCH_WEBSOCKET_URL,
            on_message=self.on_message,
            on_open=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error
        )

        # Store configuration
        self.__session_id = None
        self.__auth = auth_server
        self._bot_id = bot_id
        self._channel_id = channel_id
        self._subscription_types = subscription_types[:]
        self.__channel_point_subscription = channel_point_subscription or []

        # Rate limiting and connection management
        self.keep_running = True
        self.__connection_attempts = []
        self.__subscription_attempts = []
        self.__last_429_error = None
        self.__backoff_until = None
        self.__max_retries = 3
        self.__current_retry = 0

        # Subscription delay to avoid rate limits
        self.__subscription_delay = 2.0  # 2 seconds between subscriptions

        # Initialize subscription model
        try:
            self.__tsm = TwitchSubscriptionModel(self._channel_id, self._bot_id)
        except Exception as e:
            logger.error(f"Failed to initialize subscription model: {e}")
            raise TwitchEventSubError(f"Subscription model initialization failed: {e}")

        # Setup database if requested
        self.__store_in_db = store_in_db
        self.__dbmanager = None

        if self.__store_in_db:
            try:
                self.__dbmanager = DataBaseManager(db_path, start_thread=True)
                logger.info(f"Database initialized at: {db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")
                logger.warning("Continuing without database storage")
                self.__store_in_db = False

        # Setup trigger map
        self.__trigger_map = trigger_map
        if not self.__trigger_map:
            logger.warning("No trigger map provided - events will not trigger callbacks")

        logger.info(f"EventSub initialized for channel {channel_id} with rate limit protection")

    def _can_connect(self) -> bool:
        """Check if we can make a new WebSocket connection based on rate limits."""
        now = datetime.now()

        # Clean old connection attempts (older than 5 minutes)
        cutoff = now - timedelta(minutes=5)
        self.__connection_attempts = [
            attempt for attempt in self.__connection_attempts
            if attempt > cutoff
        ]

        # Check if we're in backoff period
        if self.__backoff_until and now < self.__backoff_until:
            remaining = (self.__backoff_until - now).total_seconds()
            logger.warning(f"In backoff period. {remaining:.1f} seconds remaining")
            return False

        # Check connection rate limit (3 per 5 minutes)
        if len(self.__connection_attempts) >= 3:
            logger.warning(f"Connection rate limit reached ({len(self.__connection_attempts)}/3 per 5 minutes)")
            return False

        return True

    def _record_connection_attempt(self):
        """Record a connection attempt for rate limiting."""
        self.__connection_attempts.append(datetime.now())
        logger.debug(f"Connection attempts in last 5min: {len(self.__connection_attempts)}")

    def _can_subscribe(self) -> bool:
        """Check if we can make new subscriptions based on rate limits."""
        now = datetime.now()

        # Clean old subscription attempts (older than 10 seconds)
        cutoff = now - timedelta(seconds=10)
        self.__subscription_attempts = [
            attempt for attempt in self.__subscription_attempts
            if attempt > cutoff
        ]

        # Check subscription rate limit (10 per 10 seconds)
        if len(self.__subscription_attempts) >= 10:
            logger.warning(f"Subscription rate limit reached ({len(self.__subscription_attempts)}/10 per 10 seconds)")
            return False

        return True

    def _record_subscription_attempt(self):
        """Record a subscription attempt for rate limiting."""
        self.__subscription_attempts.append(datetime.now())
        logger.debug(f"Subscription attempts in last 10s: {len(self.__subscription_attempts)}")

    def _handle_429_error(self):
        """Handle a 429 rate limit error with exponential backoff."""
        self.__last_429_error = datetime.now()

        # Calculate backoff time (exponential backoff with jitter)
        base_backoff = 60 * (2 ** self.__current_retry)  # 60s, 120s, 240s, etc.
        max_backoff = 300  # Maximum 5 minutes
        jitter = random.uniform(10, 30)  # 10-30 seconds jitter

        backoff_seconds = min(base_backoff + jitter, max_backoff)
        self.__backoff_until = datetime.now() + timedelta(seconds=backoff_seconds)

        logger.error(f"Rate limited (429)! Backing off for {backoff_seconds:.1f} seconds until {self.__backoff_until}")
        logger.info("This is normal if you recently restarted the bot or have multiple instances running")

    def _wait_for_rate_limit(self):
        """Wait if we're currently rate limited."""
        if self.__backoff_until:
            now = datetime.now()
            if now < self.__backoff_until:
                remaining = (self.__backoff_until - now).total_seconds()
                logger.info(f"Waiting {remaining:.1f} seconds due to rate limiting...")
                time.sleep(remaining)
                logger.info("Rate limit wait period completed")

    def run_forever_with_rate_limiting(self):
        """
        Run WebSocket with rate limit aware reconnection.
        """
        logger.info("Starting EventSub with rate limit protection...")

        while self.keep_running and self.__current_retry < self.__max_retries:
            try:
                # Wait if we're rate limited
                self._wait_for_rate_limit()

                # Check if we can connect
                if not self._can_connect():
                    logger.warning("Cannot connect due to rate limits. Waiting...")
                    time.sleep(30)  # Wait 30 seconds before checking again
                    continue

                logger.info(f"EventSub connection attempt {self.__current_retry + 1}/{self.__max_retries}")

                # Record the connection attempt
                self._record_connection_attempt()

                # Attempt connection
                self.run_forever()

                # If we get here, connection was successful
                logger.info("EventSub connection completed normally")
                self.__current_retry = 0  # Reset retry counter on success
                self.__backoff_until = None  # Reset backoff

            except KeyboardInterrupt:
                logger.info("EventSub stopped by user")
                break

            except Exception as e:
                error_str = str(e).lower()

                # Handle 429 specifically
                if "429" in error_str or "too many requests" in error_str:
                    logger.error("WebSocket handshake failed: 429 Too Many Requests")
                    self._handle_429_error()
                    self.__current_retry += 1

                    if self.__current_retry < self.__max_retries:
                        logger.info(f"Will retry after backoff period ({self.__current_retry}/{self.__max_retries})")
                    else:
                        logger.error("Max retries reached due to rate limiting")
                        break
                else:
                    # Handle other errors
                    self.__current_retry += 1
                    logger.error(f"EventSub connection error: {e}")

                    if self.__current_retry < self.__max_retries:
                        # Exponential backoff for other errors
                        delay = min(2 ** self.__current_retry * 10, 120)  # 10s, 20s, 40s, max 2min
                        logger.info(f"Retrying in {delay} seconds... ({self.__current_retry}/{self.__max_retries})")
                        time.sleep(delay)
                    else:
                        logger.error("Max retries reached")
                        break

    def on_message(self, ws, message: str) -> None:
        """Handle incoming WebSocket messages."""
        try:
            logger.debug(f"Received message: {message[:200]}...")

            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {e}")
                return

            metadata = data.get("metadata", {})
            payload = data.get("payload", {})
            message_type = metadata.get("message_type")
            msg_timestamp = metadata.get("message_timestamp", "").replace("Z", "")

            if not message_type:
                logger.warning("Received message without message_type")
                return

            if message_type == "session_welcome":
                self._handle_session_welcome(payload)
            elif message_type == "notification":
                self._handle_notification(payload, msg_timestamp)
            elif message_type == "session_keepalive":
                logger.debug("Received keepalive message")
            elif message_type == "session_reconnect":
                logger.info("Received reconnect request from Twitch")
                self._handle_reconnect(payload)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
            logger.debug(f"Error traceback: {traceback.format_exc()}")

    def _handle_session_welcome(self, payload: Dict[str, Any]) -> None:
        """Handle session welcome message and initiate subscriptions."""
        try:
            logger.info("Processing session welcome message")

            session_data = payload.get("session", {})
            self.__session_id = session_data.get("id")

            if not self.__session_id:
                raise TwitchEventSubError("No session ID provided in welcome message")

            logger.info(f"Session established with ID: {self.__session_id}")

            # Reset retry counter on successful connection
            self.__current_retry = 0
            self.__backoff_until = None

            # Subscribe to all requested events with rate limiting
            self.__subscription_with_rate_limiting()

        except Exception as e:
            logger.error(f"Failed to handle session welcome: {e}")
            raise TwitchEventSubError(f"Session welcome handling failed: {e}")

    def __subscription_with_rate_limiting(self) -> None:
        """Create subscriptions with rate limit protection."""
        logger.info(f"Creating {len(self._subscription_types)} event subscriptions with rate limiting")

        for i, subscription in enumerate(self._subscription_types):
            try:
                # Check rate limits before each subscription
                while not self._can_subscribe():
                    logger.info("Subscription rate limit reached, waiting...")
                    time.sleep(2)

                logger.info(f"Creating subscription {i+1}/{len(self._subscription_types)}: {subscription}")

                # Get subscription configuration
                s_data = self.__tsm.get_subscribe_data(subscription)

                if not s_data:
                    logger.error(f"No subscription data for type: {subscription}")
                    continue

                # Check broadcaster requirements
                if s_data.get("streamer_only", False) and self._bot_id != self._channel_id:
                    raise TwitchAuthorizationFailed(
                        f"Subscription '{subscription}' requires broadcaster authentication"
                    )

                # Build subscription request
                subscription_data = {
                    "type": s_data["payload"]["type"],
                    "version": s_data["payload"]["version"],
                    "condition": s_data["payload"]["condition"].copy(),
                    "transport": {
                        "method": "websocket",
                        "session_id": self.__session_id
                    }
                }

                # Record subscription attempt
                self._record_subscription_attempt()

                # Handle special case for channel point rewards
                if subscription == TwitchSubscriptionType.CHANNEL_POINT_ACTION and self.__channel_point_subscription:
                    self._subscribe_to_channel_rewards()
                else:
                    # Standard subscription
                    response = self.__auth.post_request(
                        TwitchEndpoint.EVENTSUB_SUBSCRIPTION,
                        data=subscription_data
                    )

                    if response:
                        logger.info(f"✅ Successfully subscribed to {subscription}")
                    else:
                        logger.warning(f"⚠️ Empty response for subscription {subscription}")

                # Delay between subscriptions to avoid rate limits
                if i < len(self._subscription_types) - 1:  # Don't wait after the last one
                    logger.debug(f"Waiting {self.__subscription_delay}s before next subscription...")
                    time.sleep(self.__subscription_delay)

            except Exception as e:
                logger.error(f"Failed to subscribe to {subscription}: {e}")
                # Continue with other subscriptions
                time.sleep(1)  # Brief pause before continuing

        logger.info("✅ Subscription setup completed")

    def _subscribe_to_channel_rewards(self) -> None:
        """Subscribe to specific channel point rewards with rate limiting."""
        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_CUSTOM_REWARD,
                channel_id=self._channel_id
            )
            custom_rewards = self.__auth.get_request(endpoint).get("data", [])

            if not custom_rewards:
                logger.warning("No custom rewards found for channel")
                return

            for reward_name in self.__channel_point_subscription:
                try:
                    # Check rate limits
                    while not self._can_subscribe():
                        logger.info("Reward subscription rate limit reached, waiting...")
                        time.sleep(2)

                    logger.info(f"Subscribing to reward: {reward_name}")

                    # Find matching reward
                    reward_id = None
                    normalized_name = reward_name.replace(" ", "").lower()

                    for reward in custom_rewards:
                        reward_title_normalized = reward["title"].replace(" ", "").lower()
                        if reward_title_normalized == normalized_name:
                            reward_id = reward["id"]
                            break

                    if not reward_id:
                        logger.error(f"Custom reward '{reward_name}' not found")
                        continue

                    # Create subscription
                    subscription_data = {
                        "type": TwitchSubscriptionType.CHANNEL_POINT_ACTION,
                        "version": "1",
                        "condition": {
                            "broadcaster_user_id": self._channel_id,
                            "reward_id": reward_id
                        },
                        "transport": {
                            "method": "websocket",
                            "session_id": self.__session_id
                        }
                    }

                    self._record_subscription_attempt()

                    response = self.__auth.post_request(
                        TwitchEndpoint.EVENTSUB_SUBSCRIPTION,
                        data=subscription_data
                    )

                    if response:
                        logger.info(f"✅ Successfully subscribed to reward: {reward_name}")

                    # Delay between reward subscriptions
                    time.sleep(self.__subscription_delay)

                except Exception as e:
                    logger.error(f"Failed to subscribe to reward '{reward_name}': {e}")
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Failed to process channel reward subscriptions: {e}")

    def _handle_notification(self, payload: Dict[str, Any], timestamp: str) -> None:
        """Handle event notification messages."""
        try:
            subscription = payload.get("subscription", {})
            event = payload.get("event", {})
            subscription_type = subscription.get("type")
            subscription_id = subscription.get("id")

            if not subscription_type:
                logger.warning("Received notification without subscription type")
                return

            logger.debug(f"Processing {subscription_type} event")

            # Route to appropriate event handler
            if subscription_type == TwitchSubscriptionType.MESSAGE:
                self.__process_message(event=event, date=timestamp, id=subscription_id)
            elif subscription_type == TwitchSubscriptionType.FOLLOW:
                self.__process_follow(event=event, date=timestamp, id=subscription_id)
            # Add other event handlers as needed...

        except Exception as e:
            logger.error(f"Error processing notification: {e}")
            logger.debug(f"Error traceback: {traceback.format_exc()}")

    def __process_message(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process chat message events."""
        try:
            message_id = event['message_id']
            user_name = event["chatter_user_name"]
            user_id = event["chatter_user_id"]
            message_text = format_text(event["message"]["text"])
            cheer = bool(event.get("cheer"))
            emote = len(event["message"].get("fragments", [])) > 1

            reply_data = event.get("reply")
            thread_id = reply_data.get('thread_message_id') if reply_data else None
            parent_id = reply_data.get('parent_message_id') if reply_data else None

            # Trigger callback
            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.MESSAGE,
                    param={
                        "id": message_id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "text": message_text,
                        "cheer": cheer,
                        "emote": emote,
                        "thread_id": thread_id,
                        "parent_id": parent_id
                    }
                )

        except Exception as e:
            logger.error(f"Error processing message event: {e}")

    def __process_follow(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process follow events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.FOLLOW,
                    param={"user_id": user_id, "user_name": user_name}
                )

        except Exception as e:
            logger.error(f"Error processing follow event: {e}")

    def _handle_reconnect(self, payload: Dict[str, Any]) -> None:
        """Handle reconnection request from Twitch."""
        try:
            session_data = payload.get("session", {})
            reconnect_url = session_data.get("reconnect_url")

            if reconnect_url:
                logger.info(f"Reconnecting to: {reconnect_url}")
                self.url = reconnect_url
                self.close()
            else:
                logger.warning("Reconnect request without URL")

        except Exception as e:
            logger.error(f"Failed to handle reconnect: {e}")

    def on_error(self, ws, error) -> None:
        """Handle WebSocket errors with rate limit detection."""
        error_str = str(error).lower()

        if "429" in error_str or "too many requests" in error_str:
            logger.error("WebSocket error: 429 Too Many Requests - Rate limited!")
            logger.error("This usually means:")
            logger.error("• You restarted the bot too quickly (wait 5+ minutes)")
            logger.error("• Multiple bot instances are running")
            logger.error("• Too many subscription attempts")
        else:
            logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closure."""
        logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")

        if close_status_code == 1008:  # Policy violation (rate limit)
            logger.warning("Connection closed due to policy violation (likely rate limit)")

        # Clean up database connection
        if self.__store_in_db and self.__dbmanager:
            try:
                self.__dbmanager.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")

    def on_open(self, ws) -> None:
        """Handle WebSocket connection opening."""
        logger.info(f"✅ Connected to EventSub WebSocket: {TwitchEndpoint.TWITCH_WEBSOCKET_URL}")

    def __del__(self) -> None:
        """Cleanup when object is destroyed."""
        try:
            if self.__dbmanager:
                self.__dbmanager.close()
        except:
            pass


# Alias pour compatibilité
EventSub = RateLimitAwareEventSub