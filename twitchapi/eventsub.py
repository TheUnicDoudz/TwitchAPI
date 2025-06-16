"""
Twitch EventSub WebSocket client for real-time event notifications.

This module provides the EventSub class that connects to Twitch's EventSub WebSocket
to receive real-time notifications about channel events like messages, follows,
subscriptions, raids, and more.

Author: TheUnicDoudz
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import os
import traceback
import threading

from websocket import WebSocketApp

from twitchapi.twitchcom import (
    TwitchEndpoint,
    TriggerSignal,
    TwitchSubscriptionModel,
    TwitchSubscriptionType
)
from twitchapi.exception import TwitchEventSubError, TwitchAuthorizationFailed
from twitchapi.db import DataBaseManager, DataBaseTemplate, format_text
from twitchapi.utils import TriggerMap
from twitchapi.auth import AuthServer

logger = logging.getLogger(__name__)

# Default database path
SOURCE_ROOT = os.path.dirname(__file__)
DEFAULT_DB_PATH = os.path.join(SOURCE_ROOT, "database", "TwitchDB.db")


class ProperReconnectEventSub(WebSocketApp):
    """
    EventSub WebSocket client with proper reconnection handling.

    This implementation follows Twitch's documented reconnection flow:
    - Maintains old connection until new one is fully established
    - Handles session_reconnect messages correctly
    - Ensures no event loss during reconnection
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
        """Initialize the EventSub WebSocket client with proper reconnection."""

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

        # Core configuration
        self.__auth = auth_server
        self._bot_id = bot_id
        self._channel_id = channel_id
        self._subscription_types = subscription_types[:]
        self.__channel_point_subscription = channel_point_subscription or []

        # Session management
        self.__session_id = None
        self.__is_primary_connection = True

        # Reconnection management
        self.__reconnect_url = None
        self.__reconnect_ws = None
        self.__reconnect_thread = None
        self.__reconnect_success = False
        self.__reconnect_lock = threading.Lock()

        # Connection state
        self.keep_running = True
        self.__connection_attempts = []
        self.__subscription_attempts = []
        self.__last_429_error = None
        self.__backoff_until = None
        self.__max_retries = 3
        self.__current_retry = 0
        self.__subscription_delay = 0.5

        # Initialize components
        try:
            self.__tsm = TwitchSubscriptionModel(self._channel_id, self._bot_id)
        except Exception as e:
            logger.error(f"Failed to initialize subscription model: {e}")
            raise TwitchEventSubError(f"Subscription model initialization failed: {e}")

        # Setup database
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

        logger.info(f"EventSub initialized with proper reconnection handling")

    def on_message(self, ws, message: str) -> None:
        """Handle incoming WebSocket messages with reconnection support."""
        try:
            logger.debug(f"Received message on {'primary' if ws.sock == self.sock else 'reconnect'} connection")

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

            # Handle different message types
            if message_type == "session_welcome":
                self._handle_session_welcome(payload, ws)
            elif message_type == "notification":
                # Only process notifications on the active connection
                if self._is_active_connection(ws):
                    self._handle_notification(payload, msg_timestamp)
                else:
                    logger.debug("Ignoring notification on inactive connection")
            elif message_type == "session_keepalive":
                logger.debug(f"Keepalive on {'primary' if ws.sock == self.sock else 'reconnect'} connection")
            elif message_type == "session_reconnect":
                self._handle_reconnect_request(payload)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
            logger.debug(f"Error traceback: {traceback.format_exc()}")

    def _is_active_connection(self, ws) -> bool:
        """Determine if this is the active connection for processing events."""
        with self.__reconnect_lock:
            if self.__reconnect_ws and self.__reconnect_success:
                # Reconnection is active and successful
                return ws.sock == self.__reconnect_ws
            else:
                # Primary connection is active
                return ws.sock == self.sock

    def _handle_session_welcome(self, payload: Dict[str, Any], ws) -> None:
        """Handle session welcome message with reconnection logic."""
        try:
            session_data = payload.get("session", {})
            session_id = session_data.get("id")

            if not session_id:
                raise TwitchEventSubError("No session ID provided in welcome message")

            with self.__reconnect_lock:
                if ws.sock == self.sock:
                    # Welcome on primary connection
                    logger.info(f"Primary session established with ID: {session_id}")
                    self.__session_id = session_id
                    self.__is_primary_connection = True

                    # Subscribe to events on primary connection
                    self.__subscription_with_rate_limiting()

                elif ws.sock == self.__reconnect_ws:
                    # Welcome on reconnection
                    logger.info(f"Reconnect session established with ID: {session_id}")

                    # Update session ID for new connection
                    old_session_id = self.__session_id
                    self.__session_id = session_id

                    # Mark reconnection as successful
                    self.__reconnect_success = True

                    # Subscribe to events on new connection
                    logger.info("Setting up subscriptions on new connection...")
                    self.__subscription_with_rate_limiting()

                    # Now we can safely close the old connection
                    logger.info("New connection established successfully, closing old connection...")
                    self._close_old_connection()

                    # Promote reconnection to primary
                    self.sock = self.__reconnect_ws
                    self.__reconnect_ws = None
                    self.__is_primary_connection = True

                    logger.info(
                        f"Reconnection completed successfully! Old session: {old_session_id}, New session: {session_id}")

                else:
                    logger.warning("Received welcome on unknown connection")

        except Exception as e:
            logger.error(f"Failed to handle session welcome: {e}")
            raise TwitchEventSubError(f"Session welcome handling failed: {e}")

    def _handle_reconnect_request(self, payload: Dict[str, Any]) -> None:
        """
        Handle reconnection request according to Twitch documentation.

        Process:
        1. Extract reconnect URL from payload
        2. Create NEW WebSocket connection to reconnect URL
        3. Keep old connection alive until new one sends welcome
        4. Close old connection only after new connection is established
        """
        try:
            session_data = payload.get("session", {})
            reconnect_url = session_data.get("reconnect_url")

            if not reconnect_url:
                logger.error("Reconnect request without URL")
                return

            logger.info(f"🔄 Received reconnection request. New URL: {reconnect_url}")
            logger.info("📋 Following Twitch reconnection protocol:")
            logger.info("   1. Creating new connection to reconnect URL")
            logger.info("   2. Keeping old connection alive until new welcome")
            logger.info("   3. Will close old connection only after new connection is ready")

            with self.__reconnect_lock:
                if self.__reconnect_ws:
                    logger.warning("Reconnection already in progress, ignoring new request")
                    return

                # Store reconnect URL
                self.__reconnect_url = reconnect_url
                self.__reconnect_success = False

                # Create new WebSocket connection in separate thread
                self.__reconnect_thread = threading.Thread(
                    target=self._establish_reconnection,
                    daemon=True
                )
                self.__reconnect_thread.start()

        except Exception as e:
            logger.error(f"Failed to handle reconnect request: {e}")

    def _establish_reconnection(self) -> None:
        """Establish new WebSocket connection for reconnection."""
        try:
            logger.info("🔗 Creating new WebSocket connection for reconnection...")

            # Create new WebSocket with reconnect URL
            self.__reconnect_ws = WebSocketApp(
                self.__reconnect_url,
                on_message=self.on_message,
                on_open=self._on_reconnect_open,
                on_close=self._on_reconnect_close,
                on_error=self._on_reconnect_error
            )

            # Start the new connection
            logger.info("📡 Starting reconnection WebSocket...")
            self.__reconnect_ws.run_forever()

        except Exception as e:
            logger.error(f"Failed to establish reconnection: {e}")
            with self.__reconnect_lock:
                self.__reconnect_ws = None
                self.__reconnect_success = False

    def _on_reconnect_open(self, ws) -> None:
        """Handle reconnection WebSocket opening."""
        logger.info("✅ Reconnection WebSocket opened, waiting for welcome message...")

    def _on_reconnect_close(self, ws, close_status_code, close_msg) -> None:
        """Handle reconnection WebSocket closure."""
        logger.info(f"🔴 Reconnection WebSocket closed: {close_status_code} - {close_msg}")

        with self.__reconnect_lock:
            if not self.__reconnect_success:
                logger.error("Reconnection failed - new connection closed before welcome")
                self.__reconnect_ws = None

    def _on_reconnect_error(self, ws, error) -> None:
        """Handle reconnection WebSocket errors."""
        logger.error(f"❌ Reconnection WebSocket error: {error}")

    def _close_old_connection(self) -> None:
        """Safely close the old WebSocket connection."""
        try:
            if self.sock and self.sock != self.__reconnect_ws:
                logger.info("🔒 Closing old WebSocket connection...")

                # Close the old connection gracefully
                old_sock = self.sock
                self.sock = None  # Prevent interference

                if hasattr(old_sock, 'close'):
                    old_sock.close()

                logger.info("✅ Old connection closed successfully")
            else:
                logger.debug("No old connection to close")

        except Exception as e:
            logger.error(f"Error closing old connection: {e}")

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
            event_handlers = {
                TwitchSubscriptionType.MESSAGE: self.__process_message,
                TwitchSubscriptionType.FOLLOW: self.__process_follow,
                TwitchSubscriptionType.BAN: self.__process_ban,
                TwitchSubscriptionType.UNBAN: self.__process_unban,
                TwitchSubscriptionType.SUBSCRIBE: self.__process_subscribe,
                TwitchSubscriptionType.SUBSCRIBE_END: self.__process_end_subscribe,
                TwitchSubscriptionType.SUBGIFT: self.__process_subgift,
                TwitchSubscriptionType.RESUB_MESSAGE: self.__process_resub_message,
                TwitchSubscriptionType.RAID: self.__process_raid,
                TwitchSubscriptionType.CHANNEL_POINT_ACTION: self.__process_channel_point_action,
                TwitchSubscriptionType.CHANNEL_CHEER: self.__process_channel_cheer,
                TwitchSubscriptionType.POLL_BEGIN: self.__process_poll_begin,
                TwitchSubscriptionType.POLL_END: self.__process_poll_end,
                TwitchSubscriptionType.PREDICTION_BEGIN: self.__process_prediction_begin,
                TwitchSubscriptionType.PREDICTION_LOCK: self.__process_prediction_lock,
                TwitchSubscriptionType.PREDICTION_END: self.__process_prediction_end,
                TwitchSubscriptionType.VIP_ADD: self.__process_vip_add,
                TwitchSubscriptionType.VIP_REMOVE: self.__process_vip_remove,
                TwitchSubscriptionType.STREAM_ONLINE: self.__process_stream_online,
                TwitchSubscriptionType.STREAM_OFFLINE: self.__process_stream_offline,
                TwitchSubscriptionType.BITS: self.__process_bits
            }

            handler = event_handlers.get(subscription_type)
            if handler:
                handler(event=event, date=timestamp, id=subscription_id)
            else:
                logger.warning(f"No handler for subscription type: {subscription_type}")

        except Exception as e:
            logger.error(f"Error processing notification: {e}")
            logger.debug(f"Error traceback: {traceback.format_exc()}")

    def __subscription_with_rate_limiting(self) -> None:
        """Create subscriptions with rate limit protection."""
        logger.info(f"Creating {len(self._subscription_types)} event subscriptions with rate limiting")

        for i, subscription in enumerate(self._subscription_types):
            try:
                # Check rate limits before each subscription
                while not self._can_subscribe():
                    logger.info("Subscription rate limit reached, waiting...")
                    time.sleep(2)

                logger.info(f"Creating subscription {i + 1}/{len(self._subscription_types)}: {subscription}")

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

                # Make subscription request
                response = self.__auth.post_request(
                    TwitchEndpoint.EVENTSUB_SUBSCRIPTION,
                    data=subscription_data
                )

                if response:
                    logger.info(f"✅ Successfully subscribed to {subscription}")
                else:
                    logger.warning(f"⚠️ Empty response for subscription {subscription}")

                # Delay between subscriptions to avoid rate limits
                if i < len(self._subscription_types) - 1:
                    logger.debug(f"Waiting {self.__subscription_delay}s before next subscription...")
                    time.sleep(self.__subscription_delay)

            except Exception as e:
                logger.error(f"Failed to subscribe to {subscription}: {e}")
                time.sleep(1)

        logger.info("✅ Subscription setup completed")

    # Rate limiting methods (same as before)
    def _can_connect(self) -> bool:
        """Check if we can make a new WebSocket connection based on rate limits."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=5)
        self.__connection_attempts = [attempt for attempt in self.__connection_attempts if attempt > cutoff]

        if self.__backoff_until and now < self.__backoff_until:
            return False

        return len(self.__connection_attempts) < 3

    def _can_subscribe(self) -> bool:
        """Check if we can make new subscriptions based on rate limits."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=10)
        self.__subscription_attempts = [attempt for attempt in self.__subscription_attempts if attempt > cutoff]
        return len(self.__subscription_attempts) < 10

    def _record_connection_attempt(self):
        """Record a connection attempt for rate limiting."""
        self.__connection_attempts.append(datetime.now())

    def _record_subscription_attempt(self):
        """Record a subscription attempt for rate limiting."""
        self.__subscription_attempts.append(datetime.now())

    # Event processing methods (same as before)
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

    def __process_subscribe(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process subscription events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]
            tier = event["tier"]
            is_gift = event["is_gift"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.SUBSCRIBE,
                    param={
                        "user_id": user_id,
                        "user_name": user_name,
                        "tier": tier,
                        "is_gift": is_gift
                    }
                )

        except Exception as e:
            logger.error(f"Error processing subscribe event: {e}")

    def __process_channel_point_action(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process channel point reward events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]
            reward_name = event["reward"]["title"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.CHANNEL_POINT_ACTION,
                    param={
                        "user_id": user_id,
                        "user_name": user_name,
                        "reward_name": reward_name
                    }
                )

        except Exception as e:
            logger.error(f"Error processing channel point action: {e}")

    def __process_raid(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process raid events."""
        try:
            if event.get("to_broadcaster_user_id") == self._channel_id:
                # Incoming raid
                source = event["from_broadcaster_user_name"]
                nb_viewers = event["viewers"]

                if self.__trigger_map:
                    self.__trigger_map.trigger(
                        TriggerSignal.RAID,
                        param={"source": source, "nb_viewers": nb_viewers}
                    )

                if self.__store_in_db and self.__dbmanager:
                    self.__dbmanager.execute_script(
                        DataBaseTemplate.RAID,
                        id=id, user_source=source,
                        user_source_id=event["from_broadcaster_user_id"],
                        user_dest=event["to_broadcaster_user_name"],
                        user_dest_id=self._channel_id,
                        date=date, nb_viewer=nb_viewers
                    )
            else:
                # Outgoing raid
                dest = event["to_broadcaster_user_name"]
                nb_viewers = event["viewers"]

                if self.__trigger_map:
                    self.__trigger_map.trigger(
                        TriggerSignal.RAID_SOMEONE,
                        param={"dest": dest, "nb_viewers": nb_viewers}
                    )

                if self.__store_in_db and self.__dbmanager:
                    self.__dbmanager.execute_script(
                        DataBaseTemplate.RAID,
                        id=id, user_source=event["from_broadcaster_user_name"],
                        user_source_id=self._channel_id,
                        user_dest=dest,
                        user_dest_id=event["to_broadcaster_user_id"],
                        date=date, nb_viewer=nb_viewers
                    )

        except Exception as e:
            logger.error(f"Error processing raid event: {e}")

    def __process_ban(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process ban events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]
            moderator_name = event["moderator_user_name"]
            reason = event["reason"]
            start_ban = event["banned_at"]
            end_ban = event.get("ends_at", "")
            permanent = event["is_permanent"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.BAN,
                    param={
                        "user_id": user_id,
                        "user_name": user_name,
                        "moderator_name": moderator_name,
                        "reason": reason,
                        "start_ban": start_ban,
                        "end_ban": end_ban,
                        "permanent": permanent
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                self.__dbmanager.execute_script(
                    DataBaseTemplate.BAN,
                    id=id, user=user_name, user_id=user_id,
                    moderator=moderator_name,
                    moderator_id=event["moderator_user_id"],
                    reason=reason, start_ban=start_ban.replace("Z", ""),
                    end_ban=end_ban.replace("Z", "") if end_ban else None,
                    is_permanent=str(permanent).upper()
                )

        except Exception as e:
            logger.error(f"Error processing ban event: {e}")

    def __process_unban(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process unban events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.UNBAN,
                    param={"user_id": user_id, "user_name": user_name}
                )

        except Exception as e:
            logger.error(f"Error processing unban event: {e}")

    def __process_end_subscribe(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process subscription end events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.SUBSCRIBE_END,
                    param={"user_id": user_id, "user_name": user_name}
                )

        except Exception as e:
            logger.error(f"Error processing end subscribe event: {e}")

    def __process_subgift(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process gift subscription events."""
        try:
            total = event["total"]
            tier = event["tier"]
            is_anonymous = event["is_anonymous"]
            gifter = event["user_name"] if not is_anonymous else None
            total_gift_sub = event.get("cumulative_total") if not is_anonymous else None

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.SUBGIFT,
                    param={
                        "user_name": gifter,
                        "tier": tier,
                        "total": total,
                        "total_gift_sub": total_gift_sub,
                        "is_anonymous": is_anonymous
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                gifter_id = event["user_id"] if not is_anonymous else None
                gifter_formatted = f"'{gifter}'" if gifter else "NULL"
                gifter_id_formatted = f"'{gifter_id}'" if gifter_id else "NULL"
                total_gift_formatted = total_gift_sub if total_gift_sub is not None else "NULL"

                self.__dbmanager.execute_script(
                    DataBaseTemplate.SUBGIFT,
                    id=id, user=gifter_formatted, user_id=gifter_id_formatted,
                    date=date, tier=tier, total=total, total_gift=total_gift_formatted,
                    is_anonymous=str(is_anonymous).upper()
                )

        except Exception as e:
            logger.error(f"Error processing subgift event: {e}")

    def __process_resub_message(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process resubscription message events."""
        try:
            user_name = event["user_name"]
            user_id = event["user_id"]
            tier = event["tier"]
            streak = event.get("streak_months", 0)
            total = event.get("cumulative_months", 0)
            duration = event.get("duration_months", 1)
            message = format_text(event.get("message", {}).get("text", ""))

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.RESUB_MESSAGE,
                    param={
                        "user_name": user_name,
                        "tier": tier,
                        "streak": streak,
                        "total": total,
                        "duration": duration,
                        "message": message
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                self.__dbmanager.execute_script(
                    DataBaseTemplate.RESUB,
                    id=id, user=user_name, user_id=user_id, date=date,
                    message=message, tier=tier, streak=streak,
                    duration=duration, total=total
                )

        except Exception as e:
            logger.error(f"Error processing resub message event: {e}")

    def __process_channel_cheer(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process cheer events."""
        try:
            is_anonymous = event['is_anonymous']
            user_name = event.get("user_name") if not is_anonymous else None
            message = event.get("message", "")
            nb_bits = event["bits"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.CHANNEL_CHEER,
                    param={
                        "user_name": user_name,
                        "message": message,
                        "nb_bits": nb_bits,
                        "is_anonymous": is_anonymous
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                user_id = event.get("user_id") if not is_anonymous else None
                self.__dbmanager.execute_script(
                    DataBaseTemplate.CHANNEL_CHEER,
                    id=id, user=user_name, user_id=user_id,
                    date=date, nb_bits=nb_bits,
                    anonymous=str(is_anonymous).upper()
                )

        except Exception as e:
            logger.error(f"Error processing channel cheer event: {e}")

    def __process_poll_begin(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process poll begin events."""
        try:
            poll_title = event["title"]
            choices = event["choices"]
            bits_settings = event.get("bits_voting", {})
            channel_point_settings = event.get("channel_points_voting", {})
            start = event["started_at"]
            end = event["ends_at"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.POLL_BEGIN,
                    param={
                        "title": poll_title,
                        "choices": choices,
                        "bits_settings": bits_settings,
                        "channel_point_settings": channel_point_settings,
                        "start_date": start,
                        "end_date": end
                    }
                )

        except Exception as e:
            logger.error(f"Error processing poll begin event: {e}")

    def __process_poll_end(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process poll end events."""
        try:
            poll_title = event["title"]
            choices = event["choices"]
            status = event["status"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.POLL_END,
                    param={
                        "title": poll_title,
                        "choices": choices,
                        "status": status
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                bits_enable = event.get("bits_voting", {}).get("is_enabled", False)
                bits_amount_per_vote = event.get("bits_voting", {}).get("amount_per_vote", 0)
                channel_point_enable = event.get("channel_points_voting", {}).get("is_enabled", False)
                channel_point_amount_per_vote = event.get("channel_points_voting", {}).get("amount_per_vote", 0)
                start_date = event["started_at"].replace("Z", "")
                end_date = event["ended_at"].replace("Z", "")

                self.__dbmanager.execute_script(
                    DataBaseTemplate.POLL,
                    id=id, title=poll_title, bits_enable=bits_enable,
                    bits_amount_per_vote=bits_amount_per_vote, start_date=start_date,
                    channel_point_enable=channel_point_enable, end_date=end_date,
                    channel_point_amount_per_vote=channel_point_amount_per_vote,
                    status=status
                )

                for c in choices:
                    self.__dbmanager.execute_script(
                        DataBaseTemplate.POLL_CHOICES,
                        id=c["id"], title=c["title"],
                        bits_votes=c.get("bits_votes", 0),
                        votes=c["votes"], poll_id=id,
                        channel_points_votes=c.get("channel_points_votes", 0)
                    )

        except Exception as e:
            logger.error(f"Error processing poll end event: {e}")

    def __process_prediction_begin(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process prediction begin events."""
        try:
            pred_title = event["title"]
            choices = event["outcomes"]
            start = event["started_at"]
            lock = event["locks_at"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.PREDICTION_BEGIN,
                    param={
                        "title": pred_title,
                        "choices": choices,
                        "start_date": start,
                        "lock_date": lock
                    }
                )

        except Exception as e:
            logger.error(f"Error processing prediction begin event: {e}")

    def __process_prediction_lock(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process prediction lock events."""
        try:
            pred_title = event["title"]
            result = event["outcomes"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.PREDICTION_LOCK,
                    param={"title": pred_title, "result": result}
                )

        except Exception as e:
            logger.error(f"Error processing prediction lock event: {e}")

    def __process_prediction_end(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process prediction end events."""
        try:
            pred_title = event["title"]
            result = event["outcomes"]
            winning = None

            # Find the winning prediction
            for r in result:
                if r["id"] == event.get("winning_outcome_id"):
                    winning = r["title"]
                    break

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.PREDICTION_END,
                    param={
                        "title": pred_title,
                        "result": result,
                        "winning_pred": winning
                    }
                )

            if self.__store_in_db and self.__dbmanager and winning:
                winning_id = event.get("winning_outcome_id")
                start_date = event["started_at"].replace("Z", "")
                end_date = event["ended_at"].replace("Z", "")
                status = event["status"]

                self.__dbmanager.execute_script(
                    DataBaseTemplate.PREDICTION,
                    id=id, title=pred_title,
                    winning_outcome=winning, winning_outcome_id=winning_id,
                    start_date=start_date, end_date=end_date, status=status
                )

                for r in result:
                    self.__dbmanager.execute_script(
                        DataBaseTemplate.PREDICTION_CHOICES,
                        id=r["id"], title=r["title"],
                        nb_users=r.get("users", 0),
                        channel_points=r.get("channel_points", 0),
                        prediction_id=id
                    )

        except Exception as e:
            logger.error(f"Error processing prediction end event: {e}")

    def __process_vip_add(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process VIP add events."""
        try:
            user_name = event["user_name"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.VIP_ADD,
                    param={"user_name": user_name}
                )

            if self.__store_in_db and self.__dbmanager:
                user_id = event["user_id"]
                self.__dbmanager.execute_script(
                    DataBaseTemplate.ADD_VIP,
                    user_id=user_id, user=user_name, date=date
                )

        except Exception as e:
            logger.error(f"Error processing VIP add event: {e}")

    def __process_vip_remove(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process VIP remove events."""
        try:
            user_name = event["user_name"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.VIP_REMOVE,
                    param={"user_name": user_name}
                )

            if self.__store_in_db and self.__dbmanager:
                user_id = event["user_id"]
                self.__dbmanager.execute_script(
                    DataBaseTemplate.REMOVE_VIP,
                    user_id=user_id
                )

        except Exception as e:
            logger.error(f"Error processing VIP remove event: {e}")

    def __process_stream_online(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process stream online events."""
        try:
            stream_type = event["type"]
            start_time = event["started_at"]

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.STREAM_ONLINE,
                    param={"type": stream_type, "start_time": start_time}
                )

        except Exception as e:
            logger.error(f"Error processing stream online event: {e}")

    def __process_stream_offline(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process stream offline events."""
        try:
            if self.__trigger_map:
                self.__trigger_map.trigger(TriggerSignal.STREAM_OFFLINE)

        except Exception as e:
            logger.error(f"Error processing stream offline event: {e}")

    def __process_bits(self, event: Dict[str, Any], date: str, id: str) -> None:
        """Process bits events."""
        try:
            user_name = event["user_name"]
            bits_number = event["bits"]
            bits_type = event.get("type", "")
            power_up = event.get("power_up", "")
            message = format_text(event.get("message", {}).get("text", ""))

            if self.__trigger_map:
                self.__trigger_map.trigger(
                    TriggerSignal.BITS,
                    param={
                        "user_name": user_name,
                        "bits": bits_number,
                        "type": bits_type,
                        "power_up": power_up,
                        "message": message
                    }
                )

            if self.__store_in_db and self.__dbmanager:
                user_id = event["user_id"]
                power_up_formatted = "NULL" if not power_up else f"'{power_up}'"
                message_formatted = "NULL" if not message else f"'{message}'"

                self.__dbmanager.execute_script(
                    DataBaseTemplate.BITS,
                    id=id, user_id=user_id, user=user_name, type=bits_type,
                    nb_bits=bits_number, power_up=power_up_formatted,
                    message=message_formatted, date=date
                )

        except Exception as e:
            logger.error(f"Error processing bits event: {e}")

    def run_forever_with_proper_reconnection(self):
        """Run WebSocket with proper reconnection handling."""
        logger.info("Starting EventSub with proper reconnection handling...")

        while self.keep_running and self.__current_retry < self.__max_retries:
            try:
                if not self._can_connect():
                    logger.warning("Cannot connect due to rate limits. Waiting...")
                    time.sleep(30)
                    continue

                logger.info(f"EventSub connection attempt {self.__current_retry + 1}/{self.__max_retries}")
                self._record_connection_attempt()

                # Start primary connection
                self.run_forever()

                logger.info("EventSub connection completed normally")
                self.__current_retry = 0
                break

            except KeyboardInterrupt:
                logger.info("EventSub stopped by user")
                break

            except Exception as e:
                self.__current_retry += 1
                logger.error(f"EventSub connection error: {e}")

                if self.__current_retry < self.__max_retries:
                    delay = min(2 ** self.__current_retry * 10, 120)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error("Max retries reached")
                    break

    def on_error(self, ws, error) -> None:
        """Handle WebSocket errors."""
        connection_type = "primary" if ws.sock == self.sock else "reconnect"
        logger.error(f"WebSocket error on {connection_type} connection: {error}")

    def on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closure."""
        connection_type = "primary" if ws.sock == self.sock else "reconnect"
        logger.info(f"WebSocket {connection_type} connection closed: {close_status_code} - {close_msg}")

        # Clean up database connection
        if self.__store_in_db and self.__dbmanager:
            try:
                self.__dbmanager.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")

    def on_open(self, ws) -> None:
        """Handle WebSocket connection opening."""
        connection_type = "primary" if ws.sock == self.sock else "reconnect"
        logger.info(f"✅ {connection_type.title()} WebSocket connected to EventSub")

    def __del__(self) -> None:
        """Cleanup when object is destroyed."""
        try:
            if self.__dbmanager:
                self.__dbmanager.close()
            if self.__reconnect_ws:
                self.__reconnect_ws.close()
        except:
            pass


# Alias for compatibility
EventSub = ProperReconnectEventSub