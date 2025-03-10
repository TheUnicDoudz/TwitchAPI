class TwitchEndpoint:
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    TWITCH_WEBSOCKET_URL = "wss://eventsub.wss.twitch.tv/ws"
    TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"

    USER_ID = "users?login=<user_id>"
    CHANNEL_INFO = "channels?broadcaster_id=<channel_id>"
    SEND_MESSAGE = "chat/messages"
    EVENTSUB_SUBSCRIPTION = "eventsub/subscriptions"
    GET_CUSTOM_REWARD = "channel_points/custom_rewards?broadcaster_id=<channel_id>"
    GET_FOLLOWERS = "channels/followers?broadcaster_id=<channel_id>"
    GET_SUBSCRIBERS = "subscriptions?broadcaster_id=<channel_id>"
    GET_CHATTERS = "chat/chatters?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"
    BAN = "moderation/bans?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"

    @staticmethod
    def apply_param(endpoint: str, **kwargs):
        for param in kwargs:
            marker = f"<{param}>"
            if marker not in endpoint:
                raise AttributeError(f"{param} is not supported by the endpoint {endpoint}")
            endpoint = endpoint.replace(marker, kwargs[param])
        return endpoint


class TwitchRightType:
    USER_READ_CHAT = "user:read:chat"
    USER_BOT = "user:bot"
    USER_WRITE_CHAT = "user:write:chat"
    CHANNEL_BOT = "channel:bot"
    MODERATOR_READ_FOLLOWERS = "moderator:read:followers"
    MODERATOR_READ_CHATTERS = "moderator:read:chatters"
    CHANNEL_MODERATE = "channel:moderate"
    CHANNEL_READ_SUBSCRIPTIONS = "channel:read:subscriptions"
    CHANNEL_READ_REDEMPTIONS = "channel:read:redemptions"
    CHANNEL_MANAGE_REDEMPTIONS = "channel:manage:redemptions"
    CHANNEL_READ_POLLS = "channel:read:polls"
    CHANNEL_MANAGE_POLLS = "channel:manage:polls"
    CHANNEL_READ_PREDICTIONS = "channel:read:predictions"
    CHANNEL_MANAGE_PREDICTIONS = "channel:manage:predictions"
    CHANNEL_READ_VIPS = "channel:read:vips"
    CHANNEL_MANAGE_VIPS = "channel:manage:vips"
    BITS_READ = "bits:read"


class TwitchSubscriptionType:
    MESSAGE = "channel.chat.message"

    FOLLOW = "channel.follow"

    BAN = "channel.ban"

    SUBSCRIBE = "channel.subscribe"
    SUBGIFT = "channel.subscription.gift"
    RESUB_MESSAGE = "channel.subscription.message"

    RAID = "channel.raid"

    CHANNEL_POINT_ACTION = "channel.channel_points_custom_reward_redemption.add"
    CHANNEL_CHEER = "channel.cheer"

    POLL_BEGIN = "channel.poll.begin"
    POLL_END = "channel.poll.end"

    PREDICTION_BEGIN = "channel.prediction.begin"
    PREDICTION_LOCK = "channel.prediction.lock"
    PREDICTION_END = "channel.prediction.end"

    VIP_ADD = "channel.vip.add"
    VIP_REMOVE = "channel.vip.remove"

    STREAM_ONLINE = "stream.online"
    STREAM_OFFLINE = "stream.offline"

    BITS = "channel.bits.use"


class TwitchSubscriptionModel:

    def __init__(self, broadcaster_user_id, user_id):
        self.MESSAGE = {
            "right": [TwitchRightType.USER_READ_CHAT, TwitchRightType.USER_BOT, TwitchRightType.CHANNEL_BOT],
            "payload": {
                "type": TwitchSubscriptionType.MESSAGE,
                "condition": {"broadcaster_user_id": broadcaster_user_id, "user_id": user_id},
                "version": "1"
            },
            "streamer_only": False
        }

        self.FOLLOW = {
            "right": [TwitchRightType.MODERATOR_READ_FOLLOWERS],
            "payload": {
                "type": TwitchSubscriptionType.FOLLOW,
                "version": "2",
                "condition": {
                    "broadcaster_user_id": broadcaster_user_id,
                    "moderator_user_id": user_id
                }
            },
            "streamer_only": False
        }

        self.BAN = {
            "right": [TwitchRightType.CHANNEL_MODERATE],
            "payload": {
                "type": TwitchSubscriptionType.BAN,
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_user_id,
                }
            },
            "streamer_only": True
        }

        self.SUBSCRIBE = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.SUBSCRIBE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.SUBGIFT = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.SUBGIFT,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.RESUB_MESSAGE = {
            "right": [TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.RESUB_MESSAGE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.RAID = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"to_broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.RAID_SOMEONE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"from_broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.CHANNEL_POINT_ACTION = {
            "right": [TwitchRightType.CHANNEL_READ_REDEMPTIONS, TwitchRightType.CHANNEL_MANAGE_REDEMPTIONS],
            "payload": {
                "type": TwitchSubscriptionType.CHANNEL_POINT_ACTION,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id, "reward_id": ""}
            },
            "streamer_only": True
        }

        self.CHANNEL_CHEER = {
            "right": [TwitchRightType.BITS_READ],
            "payload": {
                "type": TwitchSubscriptionType.CHANNEL_CHEER,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.POLL_BEGIN = {
            "right": [TwitchRightType.CHANNEL_READ_POLLS, TwitchRightType.CHANNEL_MANAGE_POLLS],
            "payload": {
                "type": TwitchSubscriptionType.POLL_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.POLL_END = {
            "right": [TwitchRightType.CHANNEL_READ_POLLS, TwitchRightType.CHANNEL_MANAGE_POLLS],
            "payload": {
                "type": TwitchSubscriptionType.POLL_END,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.PREDICTION_BEGIN = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.PREDICTION_LOCK = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_LOCK,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.PREDICTION_END = {
            "right": [TwitchRightType.CHANNEL_READ_PREDICTIONS, TwitchRightType.CHANNEL_MANAGE_PREDICTIONS],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_END,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.VIP_ADD = {
            "right": [TwitchRightType.CHANNEL_READ_VIPS, TwitchRightType.CHANNEL_MANAGE_VIPS],
            "payload": {
                "type": TwitchSubscriptionType.VIP_ADD,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.VIP_REMOVE = {
            "right": [TwitchRightType.CHANNEL_READ_VIPS, TwitchRightType.CHANNEL_MANAGE_VIPS],
            "payload": {
                "type": TwitchSubscriptionType.VIP_REMOVE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

        self.STREAM_ONLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_ONLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.STREAM_OFFLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_OFFLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": False
        }

        self.BITS = {
            "right": [TwitchRightType.BITS_READ],
            "payload": {
                "type": TwitchSubscriptionType.BITS,
                "version": "beta",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            },
            "streamer_only": True
        }

    def which_right(self, subscription_list: list[str]) -> list[str]:
        rights = []

        for subscription in self.__dict__.values():
            if subscription["payload"]["type"] in subscription_list:
                rights += subscription["right"]

        return list(set(rights))

    def get_subscribe_data(self, subscription_type: str) -> dict[str, str | dict[str, str]]:
        for subscription in self.__dict__.values():
            if subscription["payload"]["type"] == subscription_type:
                return subscription


class TriggerSignal:
    MESSAGE = "message"

    FOLLOW = "follow"

    BAN = "ban"

    SUBSCRIBE = "subscribe"
    SUBGIFT = "subgift"
    RESUB_MESSAGE = "resub_message"

    RAID = "raid"
    RAID_SOMEONE = "raid_someone"

    CHANNEL_POINT_ACTION = "channel_point_action"
    CHANNEL_CHEER = "channel_cheer"

    POLL_BEGIN = "poll_begin"
    POLL_END = "poll_end"

    PREDICTION_BEGIN = "prediction_begin"
    PREDICTION_LOCK = "prediction_lock"
    PREDICTION_END = "prediction_end"

    VIP_ADD = "vip_add"
    VIP_REMOVE = "vip_remove"

    STREAM_ONLINE = "stream_online"
    STREAM_OFFLINE = "stream_offline"

    BITS = "bits"
