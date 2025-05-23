"""
Twitch API communication constants and utilities.

This module contains all the constants, endpoints, permissions, and subscription
models needed to interact with the Twitch API and EventSub system.

Author: TheUnicDoudz
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TwitchEndpoint:
    """
    Constants and utilities for Twitch API endpoints.

    This class contains all the URL templates and endpoint constants
    needed to make requests to the Twitch API.
    """

    # Base URLs for different Twitch services
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    TWITCH_WEBSOCKET_URL = "wss://eventsub.wss.twitch.tv/ws"
    TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/"

    # OAuth2 endpoints
    CODE = "authorize"
    TOKEN = "token"

    # User and channel information endpoints
    USER_ID = "users?login=<user_id>"
    CHANNEL_INFO = "channels?broadcaster_id=<channel_id>"

    # Chat and messaging endpoints
    SEND_MESSAGE = "chat/messages"
    GET_CHATTERS = "chat/chatters?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"

    # EventSub endpoints
    EVENTSUB_SUBSCRIPTION = "eventsub/subscriptions"

    # Channel points and rewards endpoints
    GET_CUSTOM_REWARD = "channel_points/custom_rewards?broadcaster_id=<channel_id>"

    # Community endpoints
    GET_FOLLOWERS = "channels/followers?broadcaster_id=<channel_id>"
    GET_SUBSCRIBERS = "subscriptions?broadcaster_id=<channel_id>"

    # Moderation endpoints
    GET_BAN = "moderation/banned?broadcaster_id=<channel_id>"
    BAN = "moderation/bans?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"

    @staticmethod
    def apply_param(endpoint: str, **kwargs) -> str:
        """
        Apply parameters to an endpoint template safely.

        This method replaces parameter placeholders in endpoint templates
        with actual values, ensuring all required parameters are provided.

        Args:
            endpoint: Endpoint template with <parameter> placeholders
            **kwargs: Parameters to substitute in the template

        Returns:
            Complete endpoint URL with parameters applied

        Raises:
            AttributeError: If a required parameter is missing
            ValueError: If endpoint or parameters are invalid

        Examples:
            # Get user info
            url = TwitchEndpoint.apply_param(
                TwitchEndpoint.USER_ID, 
                user_id="someuser"
            )

            # Get channel chatters
            url = TwitchEndpoint.apply_param(
                TwitchEndpoint.GET_CHATTERS,
                channel_id="123456",
                moderator_id="789012"
            )
        """
        if not isinstance(endpoint, str):
            raise ValueError("endpoint must be a string")

        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty")

        result_endpoint = endpoint
        used_params = set()

        for param, value in kwargs.items():
            if not isinstance(param, str):
                continue

            marker = f"<{param}>"

            if marker not in result_endpoint:
                raise AttributeError(
                    f"Parameter '{param}' is not supported by endpoint '{endpoint}'"
                )

            # Validate and format parameter value
            if value is None:
                raise ValueError(f"Parameter '{param}' cannot be None")

            # Convert value to string and URL-encode if necessary
            str_value = str(value).strip()
            if not str_value:
                raise ValueError(f"Parameter '{param}' cannot be empty")

            # Replace the parameter placeholder
            result_endpoint = result_endpoint.replace(marker, str_value)
            used_params.add(param)

        # Check for any remaining unreplaced parameters
        import re
        remaining_params = re.findall(r'<(\w+)>', result_endpoint)
        if remaining_params:
            raise AttributeError(
                f"Missing required parameters for endpoint '{endpoint}': {remaining_params}"
            )

        logger.debug(f"Applied parameters {list(used_params)} to endpoint")
        return result_endpoint


class TwitchRightType:
    """
    OAuth2 permission scopes for Twitch API access.

    These constants define the various permission scopes that can be
    requested during OAuth2 authentication. Each scope grants access
    to specific API functionality.

    Reference: https://dev.twitch.tv/docs/authentication/scopes/
    """

    # Chat permissions
    USER_READ_CHAT = "user:read:chat"
    USER_WRITE_CHAT = "user:write:chat"
    USER_BOT = "user:bot"
    CHANNEL_BOT = "channel:bot"

    # Moderation permissions  
    MODERATOR_READ_FOLLOWERS = "moderator:read:followers"
    MODERATOR_READ_CHATTERS = "moderator:read:chatters"
    MODERATOR_MANAGE_BANNED_USERS = "moderator:manage:banned_users"
    CHANNEL_MODERATE = "channel:moderate"

    # Subscription permissions
    CHANNEL_READ_SUBSCRIPTIONS = "channel:read:subscriptions"

    # Channel points and rewards permissions
    CHANNEL_READ_REDEMPTIONS = "channel:read:redemptions"
    CHANNEL_MANAGE_REDEMPTIONS = "channel:manage:redemptions"

    # Poll permissions
    CHANNEL_READ_POLLS = "channel:read:polls"
    CHANNEL_MANAGE_POLLS = "channel:manage:polls"

    # Prediction permissions
    CHANNEL_READ_PREDICTIONS = "channel:read:predictions"
    CHANNEL_MANAGE_PREDICTIONS = "channel:manage:predictions"

    # VIP permissions
    CHANNEL_READ_VIPS = "channel:read:vips"
    CHANNEL_MANAGE_VIPS = "channel:manage:vips"

    # Bits permissions
    BITS_READ = "bits:read"

    @classmethod
    def get_all_scopes(cls) -> List[str]:
        """
        Get all available permission scopes.

        Returns:
            List of all permission scope strings
        """
        scopes = []
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and attr_name.isupper():
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, str) and ':' in attr_value:
                    scopes.append(attr_value)
        return sorted(scopes)

    @classmethod
    def validate_scopes(cls, scopes: List[str]) -> List[str]:
        """
        Validate a list of permission scopes.

        Args:
            scopes: List of scope strings to validate

        Returns:
            List of valid scopes

        Raises:
            ValueError: If any scope is invalid
        """
        if not isinstance(scopes, list):
            raise ValueError("scopes must be a list")

        valid_scopes = cls.get_all_scopes()
        invalid_scopes = []

        for scope in scopes:
            if not isinstance(scope, str):
                invalid_scopes.append(str(scope))
            elif scope not in valid_scopes:
                invalid_scopes.append(scope)

        if invalid_scopes:
            raise ValueError(f"Invalid scopes: {invalid_scopes}")

        return scopes


class TwitchSubscriptionType:
    """
    EventSub subscription type constants.

    These constants define the types of events that can be subscribed to
    through Twitch's EventSub WebSocket system.

    Reference: https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/
    """

    # Chat events
    MESSAGE = "channel.chat.message"

    # Community events
    FOLLOW = "channel.follow"

    # Moderation events
    BAN = "channel.ban"
    UNBAN = "channel.unban"

    # Subscription events
    SUBSCRIBE = "channel.subscribe"
    SUBSCRIBE_END = "channel.subscription.end"
    SUBGIFT = "channel.subscription.gift"
    RESUB_MESSAGE = "channel.subscription.message"

    # Raid events
    RAID = "channel.raid"

    # Channel interaction events
    CHANNEL_POINT_ACTION = "channel.channel_points_custom_reward_redemption.add"
    CHANNEL_CHEER = "channel.cheer"

    # Poll events
    POLL_BEGIN = "channel.poll.begin"
    POLL_END = "channel.poll.end"

    # Prediction events
    PREDICTION_BEGIN = "channel.prediction.begin"
    PREDICTION_LOCK = "channel.prediction.lock"
    PREDICTION_END = "channel.prediction.end"

    # VIP events
    VIP_ADD = "channel.vip.add"
    VIP_REMOVE = "channel.vip.remove"

    # Stream status events
    STREAM_ONLINE = "stream.online"
    STREAM_OFFLINE = "stream.offline"

    # Bits events (special effects)
    BITS = "channel.bits.use"

    @classmethod
    def get_all_types(cls) -> List[str]:
        """
        Get all available subscription types.

        Returns:
            List of all subscription type strings
        """
        types = []
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and attr_name.isupper():
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, str) and '.' in attr_value:
                    types.append(attr_value)
        return sorted(types)

    @classmethod
    def validate_types(cls, subscription_types: List[str]) -> List[str]:
        """
        Validate a list of subscription types.

        Args:
            subscription_types: List of subscription type strings to validate

        Returns:
            List of valid subscription types

        Raises:
            ValueError: If any subscription type is invalid
        """
        if not isinstance(subscription_types, list):
            raise ValueError("subscription_types must be a list")

        valid_types = cls.get_all_types()
        invalid_types = []

        for sub_type in subscription_types:
            if not isinstance(sub_type, str):
                invalid_types.append(str(sub_type))
            elif sub_type not in valid_types:
                invalid_types.append(sub_type)

        if invalid_types:
            raise ValueError(f"Invalid subscription types: {invalid_types}")

        return subscription_types


class TwitchSubscriptionModel:
    """
    EventSub subscription configuration templates.

    This class provides the payload templates and permission requirements
    for each type of EventSub subscription. It handles the complex mapping
    between subscription types, required permissions, and API payload formats.
    """

    def __init__(self, broadcaster_user_id: str, user_id: str):
        """
        Initialize subscription model with user IDs.

        Args:
            broadcaster_user_id: ID of the broadcaster channel
            user_id: ID of the authenticated user (bot)

        Raises:
            ValueError: If user IDs are invalid
        """
        if not isinstance(broadcaster_user_id, str) or not broadcaster_user_id.strip():
            raise ValueError("broadcaster_user_id must be a non-empty string")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")

        self._broadcaster_user_id = broadcaster_user_id.strip()
        self._user_id = user_id.strip()

        # Initialize all subscription configurations
        self._init_subscription_configs()

        logger.debug(f"Subscription model initialized for broadcaster {broadcaster_user_id}")

    def _init_subscription_configs(self) -> None:
        """Initialize all subscription configuration dictionaries."""

        # Chat message subscription
        self.MESSAGE = {
            "right": [TwitchRightType.USER_READ_CHAT, TwitchRightType.USER_BOT, TwitchRightType.CHANNEL_BOT],
            "payload": {
                "type": TwitchSubscriptionType.MESSAGE,
                "condition": {"broadcaster_user_id": self._broadcaster_user_id, "user_id": self._user_id},
                "version": "1"
            },
            "streamer_only": False
        }

        # Follow subscription
        self.FOLLOW = {
            "right": [TwitchRightType.MODERATOR_READ_FOLLOWERS],
            "payload": {
                "type": TwitchSubscriptionType.FOLLOW,
                "version": "2",
                "condition": {
                    "broadcaster_user_id": self._broadcaster_user_id,
                    "moderator_user_id": self._user_id
                }
            },
            "streamer_only": False
        }

        # Ban subscription (requires broadcaster auth)
        self.BAN = {
            "right": [TwitchRightType.CHANNEL_MODERATE],
            "payload": {
                "type": TwitchSubscriptionType.BAN,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Unban subscription (requires broadcaster auth)
        self.UNBAN = {
            "right": [TwitchRightType.CHANNEL_MODERATE],
            "payload": {
                "type": TwitchSubscriptionType.UNBAN,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Subscription events (require broadcaster auth)
        self.SUBSCRIBE = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.SUBSCRIBE,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.SUBSCRIBE_END = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.SUBSCRIBE_END,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.SUBGIFT = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.SUBGIFT,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.RESUB_MESSAGE = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.RESUB_MESSAGE,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Raid subscriptions (no special permissions required)
        self.RAID = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"to_broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.RAID_SOMEONE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"from_broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": False
        }

        # Channel points and interactions (require broadcaster auth)
        self.CHANNEL_POINT_ACTION = {
            "right": [TwitchRightType.CHANNEL_READ_REDEMPTIONS, TwitchRightType.CHANNEL_MANAGE_REDEMPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.CHANNEL_POINT_ACTION,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id, "reward_id": ""}
            },
            "streamer_only": True
        }

        self.CHANNEL_CHEER = {
            "right": [TwitchRightType.BITS_READ],
            "payload": {
                "type": TwitchSubscriptionType.CHANNEL_CHEER,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Poll subscriptions (require broadcaster auth)
        self.POLL_BEGIN = {
            "right": [TwitchRightType.CHANNEL_READ_POLLS, TwitchRightType.CHANNEL_MANAGE_POLLS],
            "payload": {
                "type": TwitchSubscriptionType.POLL_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.POLL_END = {
            "right": [TwitchRightType.CHANNEL_READ_POLLS, TwitchRightType.CHANNEL_MANAGE_POLLS],
            "payload": {
                "type": TwitchSubscriptionType.POLL_END,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Prediction subscriptions (require broadcaster auth)
        self.PREDICTION_BEGIN = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.PREDICTION_LOCK = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_LOCK,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.PREDICTION_END = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_END,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # VIP subscriptions (require broadcaster auth)
        self.VIP_ADD = {
            "right": [TwitchRightType.CHANNEL_READ_VIPS, TwitchRightType.CHANNEL_MANAGE_VIPS],
            "payload": {
                "type": TwitchSubscriptionType.VIP_ADD,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.VIP_REMOVE = {
            "right": [TwitchRightType.CHANNEL_READ_VIPS, TwitchRightType.CHANNEL_MANAGE_VIPS],
            "payload": {
                "type": TwitchSubscriptionType.VIP_REMOVE,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

        # Stream status subscriptions (no special permissions required)
        self.STREAM_ONLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_ONLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.STREAM_OFFLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_OFFLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": False
        }

        # Bits subscription (beta version, requires broadcaster auth)
        self.BITS = {
            "right": [TwitchRightType.BITS_READ],
            "payload": {
                "type": TwitchSubscriptionType.BITS,
                "version": "beta",
                "condition": {"broadcaster_user_id": self._broadcaster_user_id}
            },
            "streamer_only": True
        }

    def which_right(self, subscription_list: List[str]) -> List[str]:
        """
        Determine required permissions for a list of subscriptions.

        This method analyzes the provided subscription types and returns
        the complete list of OAuth2 permissions needed to subscribe to
        all the specified events.

        Args:
            subscription_list: List of subscription type strings

        Returns:
            List of required permission scope strings

        Raises:
            ValueError: If subscription_list is invalid

        Example:
            model = TwitchSubscriptionModel("123456", "789012")
            rights = model.which_right([
                TwitchSubscriptionType.MESSAGE,
                TwitchSubscriptionType.FOLLOW
            ])
            # Returns: ['user:read:chat', 'user:bot', 'channel:bot', 'moderator:read:followers']
        """
        if not isinstance(subscription_list, list):
            raise ValueError("subscription_list must be a list")

        if not subscription_list:
            return []

        # Validate subscription types
        TwitchSubscriptionType.validate_types(subscription_list)

        rights = []
        unknown_subscriptions = []

        # Collect rights from each subscription
        for subscription_type in subscription_list:
            found = False

            # Check all subscription configurations
            for attr_name in dir(self):
                if attr_name.startswith('_'):
                    continue

                attr_value = getattr(self, attr_name)
                if isinstance(attr_value, dict) and "payload" in attr_value:
                    if attr_value["payload"].get("type") == subscription_type:
                        rights.extend(attr_value.get("right", []))
                        found = True
                        break

            if not found:
                unknown_subscriptions.append(subscription_type)

        if unknown_subscriptions:
            logger.warning(f"Unknown subscription types: {unknown_subscriptions}")

        # Remove duplicates while preserving order
        unique_rights = []
        seen = set()
        for right in rights:
            if right not in seen:
                unique_rights.append(right)
                seen.add(right)

        logger.debug(f"Required rights for {len(subscription_list)} subscriptions: {unique_rights}")
        return unique_rights

    def get_subscribe_data(self, subscription_type: str) -> Optional[Dict[str, Any]]:
        """
        Get subscription configuration data for a specific event type.

        Args:
            subscription_type: The event subscription type to get data for

        Returns:
            Dictionary containing subscription configuration, or None if not found

        Raises:
            ValueError: If subscription_type is invalid

        Example:
            model = TwitchSubscriptionModel("123456", "789012")
            config = model.get_subscribe_data(TwitchSubscriptionType.MESSAGE)
            # Returns configuration dict with 'right', 'payload', 'streamer_only' keys
        """
        if not isinstance(subscription_type, str) or not subscription_type.strip():
            raise ValueError("subscription_type must be a non-empty string")

        subscription_type = subscription_type.strip()

        # Search through all subscription configurations
        for attr_name in dir(self):
            if attr_name.startswith('_'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, dict) and "payload" in attr_value:
                if attr_value["payload"].get("type") == subscription_type:
                    logger.debug(f"Found subscription data for: {subscription_type}")
                    return attr_value.copy()  # Return a copy to prevent modification

        logger.warning(f"No subscription data found for type: {subscription_type}")
        return None

    def get_streamer_only_subscriptions(self) -> List[str]:
        """
        Get list of subscription types that require broadcaster authentication.

        Returns:
            List of subscription type strings that require streamer_only=True
        """
        streamer_only = []

        for attr_name in dir(self):
            if attr_name.startswith('_'):
                continue

            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, dict) and attr_value.get("streamer_only", False):
                subscription_type = attr_value.get("payload", {}).get("type")
                if subscription_type:
                    streamer_only.append(subscription_type)

        return sorted(streamer_only)

    def validate_broadcaster_permissions(self, subscription_list: List[str],
                                         bot_is_broadcaster: bool) -> List[str]:
        """
        Validate that bot has required permissions for broadcaster-only subscriptions.

        Args:
            subscription_list: List of subscription types to validate
            bot_is_broadcaster: Whether the authenticated bot is the broadcaster

        Returns:
            List of subscription types that require broadcaster auth but bot isn't broadcaster

        Raises:
            ValueError: If subscription_list is invalid
        """
        if not isinstance(subscription_list, list):
            raise ValueError("subscription_list must be a list")

        if not isinstance(bot_is_broadcaster, bool):
            raise ValueError("bot_is_broadcaster must be a boolean")

        if bot_is_broadcaster:
            return []  # No restrictions if bot is the broadcaster

        restricted_subscriptions = []
        streamer_only = self.get_streamer_only_subscriptions()

        for subscription_type in subscription_list:
            if subscription_type in streamer_only:
                restricted_subscriptions.append(subscription_type)

        return restricted_subscriptions


class TriggerSignal:
    """
    Constants for event trigger signals.

    These constants define the signal names used to trigger callback
    functions when events are received. They provide a consistent
    interface between EventSub events and bot callback methods.
    """

    # Chat and messaging signals
    MESSAGE = "message"

    # Community signals
    FOLLOW = "follow"

    # Moderation signals
    BAN = "ban"
    UNBAN = "unban"

    # Subscription signals
    SUBSCRIBE = "subscribe"
    SUBSCRIBE_END = "subscribe_end"
    SUBGIFT = "subgift"
    RESUB_MESSAGE = "resub_message"

    # Raid signals
    RAID = "raid"
    RAID_SOMEONE = "raid_someone"

    # Interaction signals
    CHANNEL_POINT_ACTION = "channel_point_action"
    CHANNEL_CHEER = "channel_cheer"

    # Poll signals
    POLL_BEGIN = "poll_begin"
    POLL_END = "poll_end"

    # Prediction signals
    PREDICTION_BEGIN = "prediction_begin"
    PREDICTION_LOCK = "prediction_lock"
    PREDICTION_END = "prediction_end"

    # VIP signals
    VIP_ADD = "vip_add"
    VIP_REMOVE = "vip_remove"

    # Stream status signals
    STREAM_ONLINE = "stream_online"
    STREAM_OFFLINE = "stream_offline"

    # Bits signals
    BITS = "bits"

    @classmethod
    def get_all_signals(cls) -> List[str]:
        """
        Get all available trigger signals.

        Returns:
            List of all trigger signal strings
        """
        signals = []
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and attr_name.isupper():
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, str):
                    signals.append(attr_value)
        return sorted(signals)

    @classmethod
    def validate_signal(cls, signal: str) -> bool:
        """
        Validate that a signal is a known trigger signal.

        Args:
            signal: Signal string to validate

        Returns:
            True if signal is valid, False otherwise
        """
        if not isinstance(signal, str):
            return False

        return signal in cls.get_all_signals()


# Utility functions for working with Twitch API constants

def get_subscription_mapping() -> Dict[str, str]:
    """
    Get mapping between subscription types and trigger signals.

    Returns:
        Dictionary mapping TwitchSubscriptionType constants to TriggerSignal constants
    """
    return {
        TwitchSubscriptionType.MESSAGE: TriggerSignal.MESSAGE,
        TwitchSubscriptionType.FOLLOW: TriggerSignal.FOLLOW,
        TwitchSubscriptionType.BAN: TriggerSignal.BAN,
        TwitchSubscriptionType.UNBAN: TriggerSignal.UNBAN,
        TwitchSubscriptionType.SUBSCRIBE: TriggerSignal.SUBSCRIBE,
        TwitchSubscriptionType.SUBSCRIBE_END: TriggerSignal.SUBSCRIBE_END,
        TwitchSubscriptionType.SUBGIFT: TriggerSignal.SUBGIFT,
        TwitchSubscriptionType.RESUB_MESSAGE: TriggerSignal.RESUB_MESSAGE,
        TwitchSubscriptionType.RAID: TriggerSignal.RAID,
        TwitchSubscriptionType.CHANNEL_POINT_ACTION: TriggerSignal.CHANNEL_POINT_ACTION,
        TwitchSubscriptionType.CHANNEL_CHEER: TriggerSignal.CHANNEL_CHEER,
        TwitchSubscriptionType.POLL_BEGIN: TriggerSignal.POLL_BEGIN,
        TwitchSubscriptionType.POLL_END: TriggerSignal.POLL_END,
        TwitchSubscriptionType.PREDICTION_BEGIN: TriggerSignal.PREDICTION_BEGIN,
        TwitchSubscriptionType.PREDICTION_LOCK: TriggerSignal.PREDICTION_LOCK,
        TwitchSubscriptionType.PREDICTION_END: TriggerSignal.PREDICTION_END,
        TwitchSubscriptionType.VIP_ADD: TriggerSignal.VIP_ADD,
        TwitchSubscriptionType.VIP_REMOVE: TriggerSignal.VIP_REMOVE,
        TwitchSubscriptionType.STREAM_ONLINE: TriggerSignal.STREAM_ONLINE,
        TwitchSubscriptionType.STREAM_OFFLINE: TriggerSignal.STREAM_OFFLINE,
        TwitchSubscriptionType.BITS: TriggerSignal.BITS
    }


def validate_api_configuration(broadcaster_id: str, bot_id: str,
                               subscriptions: List[str], scopes: List[str]) -> Dict[str, Any]:
    """
    Validate a complete Twitch API configuration.

    This function performs comprehensive validation of all API configuration
    parameters and returns a summary of any issues found.

    Args:
        broadcaster_id: Twitch broadcaster user ID
        bot_id: Twitch bot user ID  
        subscriptions: List of desired subscription types
        scopes: List of OAuth2 permission scopes

    Returns:
        Dictionary with validation results containing:
        - 'valid': Boolean indicating if configuration is completely valid
        - 'errors': List of error messages for critical issues
        - 'warnings': List of warning messages for potential issues
        - 'info': Dictionary with additional configuration information

    Example:
        result = validate_api_configuration(
            broadcaster_id="123456",
            bot_id="789012", 
            subscriptions=[TwitchSubscriptionType.MESSAGE],
            scopes=[TwitchRightType.USER_READ_CHAT]
        )

        if not result['valid']:
            print("Configuration errors:", result['errors'])
    """
    errors = []
    warnings = []
    info = {}

    # Validate user IDs
    if not isinstance(broadcaster_id, str) or not broadcaster_id.strip():
        errors.append("broadcaster_id must be a non-empty string")

    if not isinstance(bot_id, str) or not bot_id.strip():
        errors.append("bot_id must be a non-empty string")

    # Validate subscriptions
    try:
        if subscriptions:
            TwitchSubscriptionType.validate_types(subscriptions)
            info['subscription_count'] = len(subscriptions)
        else:
            warnings.append("No subscriptions specified - bot will not receive events")
    except ValueError as e:
        errors.append(f"Invalid subscriptions: {e}")

    # Validate scopes
    try:
        if scopes:
            TwitchRightType.validate_scopes(scopes)
            info['scope_count'] = len(scopes)
        else:
            errors.append("No OAuth2 scopes specified")
    except ValueError as e:
        errors.append(f"Invalid scopes: {e}")

    # Check subscription-scope compatibility
    if not errors and subscriptions and scopes:
        try:
            model = TwitchSubscriptionModel(broadcaster_id, bot_id)
            required_rights = model.which_right(subscriptions)
            missing_rights = [right for right in required_rights if right not in scopes]

            if missing_rights:
                errors.append(f"Missing required scopes for subscriptions: {missing_rights}")

            # Check broadcaster-only restrictions
            bot_is_broadcaster = (broadcaster_id == bot_id)
            restricted = model.validate_broadcaster_permissions(subscriptions, bot_is_broadcaster)

            if restricted:
                if bot_is_broadcaster:
                    info['broadcaster_only_subs'] = restricted
                else:
                    errors.append(
                        f"Bot is not broadcaster but trying to subscribe to broadcaster-only events: {restricted}")

        except Exception as e:
            errors.append(f"Error validating subscription compatibility: {e}")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'info': info
    }