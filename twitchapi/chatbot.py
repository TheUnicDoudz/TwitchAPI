"""
Twitch ChatBot module for creating interactive Twitch bots.

This module provides the main ChatBot class that handles Twitch API interactions,
EventSub WebSocket connections, and provides callback methods for various Twitch events.

Author: TheUnicDoudz
"""

import logging
import time
from typing import List, Optional, Dict, Any

from twitchapi.twitchcom import (
    TwitchEndpoint,
    TriggerSignal,
    TwitchSubscriptionModel,
    TwitchRightType
)
from twitchapi.exception import (
    TwitchMessageNotSentWarning,
    KillThreadException,
    TwitchAuthorizationFailed,
    TwitchEndpointError
)
from twitchapi.auth import AuthServer, REDIRECT_URI_AUTH, DEFAULT_TIMEOUT, ACCESS_TOKEN_FILE
from twitchapi.utils import ThreadWithExc, TriggerMap
from twitchapi.eventsub import EventSub

logger = logging.getLogger(__name__)


class ChatBot:
    """
    Main class for creating Twitch bots.

    This class handles all aspects of bot creation including:
    - OAuth2 authentication with Twitch
    - EventSub WebSocket connection for real-time events
    - API requests to Twitch
    - Event callbacks that can be overridden
    - Database storage (optional)

    The bot automatically manages authentication, token refresh, and reconnections.
    """

    # Default permissions required for all methods making requests to the Twitch API
    DEFAULT_RIGHTS = [
        TwitchRightType.MODERATOR_READ_FOLLOWERS,
        TwitchRightType.USER_WRITE_CHAT,
        TwitchRightType.MODERATOR_READ_CHATTERS,
        TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS,
        TwitchRightType.MODERATOR_MANAGE_BANNED_USERS
    ]

    def __init__(self,
                 client_id: str,
                 client_secret: str,
                 bot_name: str,
                 channel_name: str,
                 subscriptions: Optional[List[str]] = None,
                 token_file_path: str = ACCESS_TOKEN_FILE,
                 redirect_uri_auth: str = REDIRECT_URI_AUTH,
                 timeout: int = DEFAULT_TIMEOUT,
                 right: Optional[List[str]] = None,
                 channel_point_subscription: Optional[List[str]] = None,
                 store_in_db: bool = False):
        """
        Initialize the Twitch ChatBot.

        Args:
            client_id: Twitch application ID
            client_secret: Twitch application secret
            bot_name: Name of the bot Twitch account
            channel_name: Name of the broadcaster channel to monitor
            subscriptions: List of event subscriptions the bot will listen for
            token_file_path: Path to save authentication tokens
            redirect_uri_auth: OAuth2 callback URI
            timeout: Authentication timeout in seconds
            right: Custom list of permissions (if None, auto-determined from subscriptions)
            channel_point_subscription: List of specific channel reward names to subscribe to
            store_in_db: Whether to store all events in SQLite database

        Raises:
            ValueError: If required parameters are missing or invalid
            TwitchAuthorizationFailed: If authentication fails
        """
        # Input validation
        if not client_id or not isinstance(client_id, str):
            raise ValueError("client_id must be a non-empty string")
        if not client_secret or not isinstance(client_secret, str):
            raise ValueError("client_secret must be a non-empty string")
        if not bot_name or not isinstance(bot_name, str):
            raise ValueError("bot_name must be a non-empty string")
        if not channel_name or not isinstance(channel_name, str):
            raise ValueError("channel_name must be a non-empty string")

        self._client_id = client_id
        self.__client_secret = client_secret
        self._bot_name = bot_name.lower()  # Normalize to lowercase
        self._channel_name = channel_name.lower()  # Normalize to lowercase

        logger.info(f"Initializing ChatBot for channel: {channel_name}")

        # Store subscription configuration
        self.__subscription = subscriptions or []
        self.__channel_point_subscription = channel_point_subscription or []

        # Determine required permissions
        if not right and self.__subscription:
            try:
                subscription_model = TwitchSubscriptionModel("test", "test")
                self.__right = subscription_model.which_right(self.__subscription)
            except Exception as e:
                logger.warning(f"Failed to auto-determine rights: {e}")
                self.__right = []
        elif right:
            self.__right = right[:]  # Create copy
        else:
            self.__right = []

        # Add default permissions
        self.__right.extend(self.DEFAULT_RIGHTS)
        # Remove duplicates while preserving order
        seen = set()
        self.__right = [x for x in self.__right if not (x in seen or seen.add(x))]

        logger.debug(f"Required permissions: {self.__right}")

        # Initialize authentication
        try:
            self.__auth = AuthServer()
            self.__auth.authentication(
                client_id=client_id,
                client_secret=client_secret,
                scope=self.__right,
                token_file_path=token_file_path,
                timeout=timeout,
                redirect_uri=redirect_uri_auth
            )
            logger.info("Authentication successful")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise TwitchAuthorizationFailed(f"Failed to authenticate: {e}")

        # Get bot and channel IDs
        try:
            self._bot_id = self._get_id(bot_name)
            logger.debug(f"Bot ID: {self._bot_id}")

            self._channel_id = self._get_id(channel_name)
            logger.debug(f"Channel ID: {self._channel_id}")
        except Exception as e:
            logger.error(f"Failed to get user IDs: {e}")
            raise TwitchEndpointError(f"Failed to retrieve user information: {e}")

        # Initialize EventSub connection if subscriptions are provided
        self.__event_sub = None
        self.__thread = None

        if subscriptions:
            try:
                self._setup_event_subscriptions(store_in_db)
                logger.info("EventSub connection initialized")
            except Exception as e:
                logger.error(f"Failed to setup EventSub: {e}")
                # Don't raise here, allow bot to work without EventSub
                logger.warning("Bot will continue without EventSub functionality")

    def _setup_event_subscriptions(self, store_in_db: bool) -> None:
        """
        Setup EventSub WebSocket connection and event triggers.

        Args:
            store_in_db: Whether to store events in database
        """
        # Create trigger map linking events to callback methods
        self.__trigger_map = TriggerMap()

        # Register all available event callbacks
        event_mappings = [
            (self.receive_message, TriggerSignal.MESSAGE),
            (self.new_follow, TriggerSignal.FOLLOW),
            (self.new_ban, TriggerSignal.BAN),
            (self.new_unban, TriggerSignal.UNBAN),
            (self.new_subscribe, TriggerSignal.SUBSCRIBE),
            (self.end_subscribe, TriggerSignal.SUBSCRIBE_END),
            (self.new_subgift, TriggerSignal.SUBGIFT),
            (self.new_resub, TriggerSignal.RESUB_MESSAGE),
            (self.raid_on_caster, TriggerSignal.RAID),
            (self.raid_someone, TriggerSignal.RAID_SOMEONE),
            (self.channel_reward, TriggerSignal.CHANNEL_POINT_ACTION),
            (self.channel_cheer, TriggerSignal.CHANNEL_CHEER),
            (self.new_poll, TriggerSignal.POLL_BEGIN),
            (self.poll_end, TriggerSignal.POLL_END),
            (self.new_prediction, TriggerSignal.PREDICTION_BEGIN),
            (self.prediction_lock, TriggerSignal.PREDICTION_LOCK),
            (self.prediction_end, TriggerSignal.PREDICTION_END),
            (self.new_vip, TriggerSignal.VIP_ADD),
            (self.remove_vip, TriggerSignal.VIP_REMOVE),
            (self.stream_online, TriggerSignal.STREAM_ONLINE),
            (self.stream_offline, TriggerSignal.STREAM_OFFLINE),
            (self.new_bits, TriggerSignal.BITS)
        ]

        for callback, signal in event_mappings:
            try:
                self.__trigger_map.add_trigger(callback, signal)
            except Exception as e:
                logger.warning(f"Failed to register callback for {signal}: {e}")

        # Initialize EventSub WebSocket
        self.__event_sub = EventSub(
            bot_id=self._bot_id,
            channel_id=self._channel_id,
            subscription_types=self.__subscription,
            auth_server=self.__auth,
            trigger_map=self.__trigger_map,
            channel_point_subscription=self.__channel_point_subscription,
            store_in_db=store_in_db
        )

        # Start EventSub in separate thread
        self.__thread = ThreadWithExc(target=self.__run_event_server)
        self.__thread.daemon = True
        self.__thread.start()

    def _get_id(self, user_name: str) -> str:
        """
        Get the Twitch ID for a username.

        Args:
            user_name: Twitch username

        Returns:
            Twitch user ID

        Raises:
            TwitchEndpointError: If user not found or API error
        """
        if not user_name or not isinstance(user_name, str):
            raise ValueError("user_name must be a non-empty string")

        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.USER_ID,
                user_id=user_name.lower()
            )
            data = self.__auth.get_request(endpoint=endpoint)

            if not data.get('data'):
                raise TwitchEndpointError(f"User '{user_name}' not found")

            user_id = data['data'][0]['id']
            logger.debug(f"Retrieved ID for {user_name}: {user_id}")
            return user_id

        except Exception as e:
            logger.error(f"Failed to get ID for user {user_name}: {e}")
            raise TwitchEndpointError(f"Failed to get user ID: {e}")

    def send_message(self, message: str, reply_message_id: Optional[str] = None) -> bool:
        """
        Send a message to the broadcaster's chat.

        Args:
            message: Message text to send
            reply_message_id: Optional ID of message to reply to

        Returns:
            True if message was sent successfully, False otherwise

        Raises:
            TwitchMessageNotSentWarning: If message couldn't be sent
            ValueError: If message is invalid
        """
        if not message or not isinstance(message, str):
            raise ValueError("message must be a non-empty string")

        if len(message) > 500:  # Twitch message limit
            logger.warning(f"Message truncated from {len(message)} to 500 characters")
            message = message[:500]

        try:
            data = {
                "broadcaster_id": self._channel_id,
                "sender_id": self._bot_id,
                "message": message,
            }

            if reply_message_id:
                data["reply_parent_message_id"] = reply_message_id

            response_data = self.__auth.post_request(
                endpoint=TwitchEndpoint.SEND_MESSAGE,
                data=data
            )

            if not response_data.get('data'):
                raise TwitchMessageNotSentWarning("No response data received")

            message_data = response_data['data'][0]

            if not message_data.get("is_sent", False):
                drop_reason = message_data.get("drop_reason", {})
                drop_code = drop_reason.get("code", "unknown")
                drop_message = drop_reason.get("message", "No reason provided")

                logger.warning(f"Message not sent: {drop_code} - {drop_message}")
                raise TwitchMessageNotSentWarning(f"{drop_code}: {drop_message}")

            logger.debug(f"Message sent successfully: {message[:50]}...")
            return True

        except TwitchMessageNotSentWarning:
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            raise TwitchEndpointError(f"Failed to send message: {e}")

    def __run_event_server(self) -> None:
        """
        Run the EventSub WebSocket server with automatic reconnection.

        This method runs in a separate thread and handles reconnection
        attempts if the WebSocket connection is lost.
        """
        max_retries = 5
        retry_delay = 30  # seconds
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.info(f"Starting EventSub server (attempt {retry_count + 1})")
                self.__event_sub.run_forever()
                break  # Exit if run_forever completes normally

            except KillThreadException:
                logger.info("EventSub server stopped by request")
                break

            except Exception as e:
                retry_count += 1
                logger.error(f"EventSub server error: {e}")

                if retry_count < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    # Exponential backoff
                    retry_delay = min(retry_delay * 2, 300)  # Max 5 minutes
                else:
                    logger.error("Max retries reached, EventSub server stopped")

    def stop_event_server(self) -> None:
        """
        Stop the EventSub WebSocket server.

        This method safely shuts down the EventSub connection and
        terminates the background thread.
        """
        try:
            if self.__event_sub:
                logger.info("Stopping EventSub server...")
                self.__event_sub.keep_running = False

            if self.__thread and self.__thread.is_alive():
                logger.info("Terminating EventSub thread...")
                self.__thread.raise_exc(KillThreadException)
                self.__thread.join(timeout=10.0)

                if self.__thread.is_alive():
                    logger.warning("EventSub thread did not terminate gracefully")
                else:
                    logger.info("EventSub server stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping EventSub server: {e}")

    def get_subscriber(self) -> List[Dict[str, Any]]:
        """
        Get all subscribers of the broadcaster channel.

        Returns:
            List of subscriber data dictionaries

        Raises:
            TwitchEndpointError: If API request fails
        """
        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_SUBSCRIBERS,
                channel_id=self._channel_id
            )
            return self.__browse_all(self.__auth.get_request, endpoint)
        except Exception as e:
            logger.error(f"Failed to get subscribers: {e}")
            raise TwitchEndpointError(f"Failed to retrieve subscribers: {e}")

    def get_follower(self) -> List[Dict[str, Any]]:
        """
        Get all followers of the broadcaster channel.

        Returns:
            List of follower data dictionaries

        Raises:
            TwitchEndpointError: If API request fails
        """
        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_FOLLOWERS,
                channel_id=self._channel_id
            )
            return self.__browse_all(self.__auth.get_request, endpoint)
        except Exception as e:
            logger.error(f"Failed to get followers: {e}")
            raise TwitchEndpointError(f"Failed to retrieve followers: {e}")

    def get_ban_user(self) -> List[Dict[str, Any]]:
        """
        Get all users banned from the broadcaster channel.

        Returns:
            List of banned user data dictionaries

        Raises:
            TwitchEndpointError: If API request fails
        """
        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_BAN,
                channel_id=self._channel_id
            )
            return self.__browse_all(self.__auth.get_request, endpoint)
        except Exception as e:
            logger.error(f"Failed to get banned users: {e}")
            raise TwitchEndpointError(f"Failed to retrieve banned users: {e}")

    def get_connected_users(self) -> List[Dict[str, Any]]:
        """
        Get all users currently connected to the broadcaster's stream.

        Returns:
            List of connected user data dictionaries

        Raises:
            TwitchEndpointError: If API request fails
        """
        try:
            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_CHATTERS,
                channel_id=self._channel_id,
                moderator_id=self._bot_id
            )
            return self.__browse_all(self.__auth.get_request, endpoint)
        except Exception as e:
            logger.error(f"Failed to get connected users: {e}")
            raise TwitchEndpointError(f"Failed to retrieve connected users: {e}")

    def __browse_all(self, callback, endpoint: str) -> List[Dict[str, Any]]:
        """
        Handle paginated API responses to retrieve all data.

        Args:
            callback: API request function to call
            endpoint: API endpoint URL

        Returns:
            Complete list of data from all pages

        Note:
            For more information: https://dev.twitch.tv/docs/api/guide/#pagination
        """
        try:
            # Add pagination parameters
            if "?" not in endpoint:
                endpoint += "?first=100"
            else:
                endpoint += "&first=100"

            # Get first page
            response = callback(endpoint)
            data = response.get("data", [])

            # Get remaining pages
            while response.get("pagination"):
                cursor = response["pagination"]["cursor"]
                paginated_endpoint = f"{endpoint}&after={cursor}"

                response = callback(paginated_endpoint)
                data.extend(response.get("data", []))

            logger.debug(f"Retrieved {len(data)} items from paginated endpoint")
            return data

        except Exception as e:
            logger.error(f"Error in paginated request: {e}")
            raise

    def ban_user(self, user_name: str, reason: str, duration: Optional[int] = None) -> bool:
        """
        Ban or timeout a user.

        Args:
            user_name: Username to ban
            reason: Reason for the ban
            duration: Ban duration in seconds (None for permanent ban)

        Returns:
            True if ban was successful, False otherwise

        Raises:
            ValueError: If parameters are invalid
            TwitchEndpointError: If API request fails
        """
        if not user_name or not isinstance(user_name, str):
            raise ValueError("user_name must be a non-empty string")
        if not reason or not isinstance(reason, str):
            raise ValueError("reason must be a non-empty string")
        if duration is not None and (not isinstance(duration, int) or duration < 1):
            raise ValueError("duration must be a positive integer")

        try:
            target_user_id = self._get_id(user_name)

            data = {
                "user_id": target_user_id,
                "reason": reason
            }

            if duration:
                data["duration"] = duration

            endpoint = TwitchEndpoint.apply_param(
                TwitchEndpoint.BAN,
                channel_id=self._channel_id,
                moderator_id=self._bot_id
            )

            self.__auth.post_request(endpoint, data=data)

            action = f"timeout ({duration}s)" if duration else "ban"
            logger.info(f"Successfully {action} user {user_name}: {reason}")
            return True

        except Exception as e:
            logger.error(f"Failed to ban user {user_name}: {e}")
            raise TwitchEndpointError(f"Failed to ban user: {e}")

    # Event callback methods - Override these in your bot subclass

    def receive_message(self, id: str, user_id: str, user_name: str, text: str,
                        cheer: bool, emote: bool, thread_id: str, parent_id: str) -> None:
        """
        Callback triggered when a chat message is received.

        Override this method in your bot subclass to handle chat messages.

        Args:
            id: Message ID
            user_id: User ID who sent the message
            user_name: Username who sent the message
            text: Message text content
            cheer: True if message contains bits/cheer
            emote: True if message contains emotes
            thread_id: Thread ID if message is part of a thread
            parent_id: Parent message ID if this is a reply
        """
        pass

    def channel_reward(self, user_id: str, user_name: str, reward_name: str) -> None:
        """
        Callback triggered when a channel point reward is redeemed.

        Override this method in your bot subclass to handle channel point rewards.

        Args:
            user_id: User ID who redeemed the reward
            user_name: Username who redeemed the reward
            reward_name: Name of the redeemed reward
        """
        pass

    def channel_cheer(self, user_name: str, message: str, nb_bits: int, is_anonymous: bool) -> None:
        """
        Callback triggered when bits are cheered.

        Override this method in your bot subclass to handle bit donations.

        Args:
            user_name: Username who sent bits (None if anonymous)
            message: Message sent with the bits
            nb_bits: Number of bits sent
            is_anonymous: True if the cheer was anonymous
        """
        pass

    def new_follow(self, user_id: str, user_name: str) -> None:
        """
        Callback triggered when someone follows the channel.

        Override this method in your bot subclass to handle new followers.

        Args:
            user_id: User ID of the new follower
            user_name: Username of the new follower
        """
        pass

    def new_subscribe(self, user_id: str, user_name: str, tier: str, is_gift: bool) -> None:
        """
        Callback triggered when someone subscribes to the channel.

        Override this method in your bot subclass to handle new subscriptions.

        Args:
            user_id: User ID of the subscriber
            user_name: Username of the subscriber
            tier: Subscription tier ("1000" = Tier 1, "2000" = Tier 2, "3000" = Tier 3)
            is_gift: True if this is a gift subscription
        """
        pass

    def end_subscribe(self, user_id: str, user_name: str) -> None:
        """
        Callback triggered when a subscription ends.

        Override this method in your bot subclass to handle subscription endings.

        Args:
            user_id: User ID whose subscription ended
            user_name: Username whose subscription ended
        """
        pass

    def new_subgift(self, user_name: str, tier: str, total: int, total_gift_sub: int, is_anonymous: bool) -> None:
        """
        Callback triggered when gift subscriptions are given.

        Override this method in your bot subclass to handle gift subscriptions.

        Args:
            user_name: Username who gave the gifts (None if anonymous)
            tier: Subscription tier being gifted
            total: Number of subscriptions gifted in this event
            total_gift_sub: Total gifts given by this user (None if anonymous)
            is_anonymous: True if the gifter is anonymous
        """
        pass

    def new_resub(self, user_name: str, tier: str, streak: int, total: int, duration: int, message: str) -> None:
        """
        Callback triggered when someone resubscribes.

        Override this method in your bot subclass to handle resubscriptions.

        Args:
            user_name: Username who resubscribed
            tier: Subscription tier
            streak: Consecutive months subscribed
            total: Total months subscribed (cumulative)
            duration: Length of this subscription
            message: Message attached to the resubscription
        """
        pass

    def raid_on_caster(self, source: str, nb_viewers: int) -> None:
        """
        Callback triggered when the channel receives a raid.

        Override this method in your bot subclass to handle incoming raids.

        Args:
            source: Username of the channel that raided
            nb_viewers: Number of viewers in the raid
        """
        pass

    def raid_someone(self, dest: str, nb_viewers: int) -> None:
        """
        Callback triggered when the channel raids another channel.

        Override this method in your bot subclass to handle outgoing raids.

        Args:
            dest: Username of the channel being raided
            nb_viewers: Number of viewers in the raid
        """
        pass

    def new_poll(self, title: str, choices: dict, bits_settings: dict,
                 channel_point_settings: dict, start_date: str, end_date: str) -> None:
        """
        Callback triggered when a new poll starts.

        Override this method in your bot subclass to handle poll events.

        Args:
            title: Poll title
            choices: Available poll choices
            bits_settings: Bits voting configuration
            channel_point_settings: Channel points voting configuration
            start_date: Poll start timestamp
            end_date: Poll end timestamp
        """
        pass

    def poll_end(self, title: str, choices: dict, status: str) -> None:
        """
        Callback triggered when a poll ends.

        Override this method in your bot subclass to handle poll results.

        Args:
            title: Poll title
            choices: Poll results with vote counts
            status: Poll end status ("completed", "archived", or "terminated")
        """
        pass

    def new_prediction(self, title: str, choices: dict, start_date: str, lock_date: str) -> None:
        """
        Callback triggered when a new prediction starts.

        Override this method in your bot subclass to handle prediction events.

        Args:
            title: Prediction title
            choices: Available prediction outcomes
            start_date: Prediction start timestamp
            lock_date: When betting locks timestamp
        """
        pass

    def prediction_lock(self, title: str, result: dict) -> None:
        """
        Callback triggered when prediction betting is locked.

        Override this method in your bot subclass to handle prediction locking.

        Args:
            title: Prediction title
            result: Current prediction state
        """
        pass

    def prediction_end(self, title: str, result: dict, winning_pred: str) -> None:
        """
        Callback triggered when a prediction ends.

        Override this method in your bot subclass to handle prediction results.

        Args:
            title: Prediction title
            result: Final prediction results
            winning_pred: Name of the winning outcome
        """
        pass

    def new_ban(self, user_id: str, user_name: str, moderator_name: str, reason: str,
                start_ban: str, end_ban: str, permanent: bool) -> None:
        """
        Callback triggered when a user is banned.

        Override this method in your bot subclass to handle ban events.

        Args:
            user_id: ID of banned user
            user_name: Name of banned user
            moderator_name: Name of moderator who issued the ban
            reason: Reason for the ban
            start_ban: Ban start timestamp
            end_ban: Ban end timestamp (if not permanent)
            permanent: True if this is a permanent ban
        """
        pass

    def new_unban(self, user_id: str, user_name: str) -> None:
        """
        Callback triggered when a user is unbanned.

        Override this method in your bot subclass to handle unban events.

        Args:
            user_id: ID of unbanned user
            user_name: Name of unbanned user
        """
        pass

    def new_vip(self, user_name: str) -> None:
        """
        Callback triggered when someone is given VIP status.

        Override this method in your bot subclass to handle VIP additions.

        Args:
            user_name: Username who was given VIP status
        """
        pass

    def remove_vip(self, user_name: str) -> None:
        """
        Callback triggered when someone loses VIP status.

        Override this method in your bot subclass to handle VIP removals.

        Args:
            user_name: Username who lost VIP status
        """
        pass

    def stream_online(self, type: str, start_time: str) -> None:
        """
        Callback triggered when the stream goes online.

        Override this method in your bot subclass to handle stream start events.

        Args:
            type: Stream type ("live", "playlist", "watch_party", "premiere", or "rerun")
            start_time: Stream start timestamp
        """
        pass

    def stream_offline(self) -> None:
        """
        Callback triggered when the stream goes offline.

        Override this method in your bot subclass to handle stream end events.
        """
        pass

    def new_bits(self, user_name: str, bits: int, type: str, power_up: str, message: str) -> None:
        """
        Callback triggered when bits are used for special effects.

        Override this method in your bot subclass to handle bit effects.

        Args:
            user_name: Username who sent the bits
            bits: Number of bits used
            type: Effect type ("message_effect", "celebration", or "gigantify_an_emote")
            power_up: Power-up data if a power-up was used
            message: Message sent with the bits (if any)
        """
        pass

    def __del__(self) -> None:
        """Cleanup when bot object is destroyed."""
        try:
            self.stop_event_server()
        except:
            pass  # Ignore errors during cleanup