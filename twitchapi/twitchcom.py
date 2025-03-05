class TwitchEndpoint:
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    TWITCH_WEBSOCKET_URL = "wss://eventsub.wss.twitch.tv/ws"
    TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"

    USER_ID = "users?login=<user_id>"
    CHANNEL_INFO = "channels?broadcaster_id=<channel_id>"
    SEND_MESSAGE = "chat/messages"
    EVENTSUB_SUBSCRIPTION = "eventsub/subscriptions"
    GET_CUSTOM_REWARD = "channel_points/custom_rewards?broadcaster_id=<user_id>"
    GET_FOLLOWERS = "channels/followers?broadcaster_id=<user_id>"
    GET_CHATTERS = "chat/chatters?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"
    BAN = "moderation/bans?broadcaster_id=<channel_id>&moderator_id=<moderator_id>"

    @staticmethod
    def apply_param(endpoint:str, **kwargs):
        for param in kwargs:
            marker = f"<{param}>"
            if marker not in endpoint:
                raise AttributeError(f"{param} is not supported by the endpoint {endpoint}")
            endpoint = endpoint.replace(marker, kwargs[param])
        return endpoint


class TwitchSubscriptionType:
    MESSAGE = "channel.chat.message"

    FOLLOW = "channel.follow"

    BAN = "channel.ban"

    SUBSCRIBE = "channel.subscribe"
    SUBGIFT = "channel.subscription.gift"
    RESUB_MESSAGE = "channel.subscription.message"

    RAID = "channel.raid"

    CHANNEL_POINT_ACTION = "channel.channel_points_custom_reward_redemption.add"

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
            "right": ["user:read:chat", "user:bot", "channel:bot"],
            "payload": {
                "type": TwitchSubscriptionType.MESSAGE,
                "condition": {"broadcaster_user_id": broadcaster_user_id, "user_id": user_id},
                "version": "1"
            }
        }

        self.FOLLOW = {
            "right": ["moderator:read:followers"],
            "payload": {
                "type": TwitchSubscriptionType.FOLLOW,
                "version": "2",
                "condition": {
                    "broadcaster_user_id": broadcaster_user_id,
                    "moderator_user_id": user_id
                }
            }
        }

        self.BAN = {
            "right": ["channel:moderate"],
            "payload": {
                "type": TwitchSubscriptionType.BAN,
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_user_id,
                }
            }
        }

        self.SUBSCRIBE = {
            "right": ["channel:read:subscriptions"],
            "payload": {
                "type": TwitchSubscriptionType.SUBSCRIBE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.SUBGIFT = {
            "right": ["channel:read:subscriptions"],
            "payload": {
                "type": TwitchSubscriptionType.SUBGIFT,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.RESUB_MESSAGE = {
            "right": ["channel:read:subscriptions"],
            "payload": {
                "type": TwitchSubscriptionType.RESUB_MESSAGE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.RAID = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"to_broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.RAID_SOMEONE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.RAID,
                "version": "1",
                "condition": {"from_broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.CHANNEL_POINT_ACTION = {
            "right": ["channel:read:redemptions", "channel:manage:redemptions"],
            "payload": {
                "type": TwitchSubscriptionType.CHANNEL_POINT_ACTION,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id, "reward_id": ""}
            }
        }

        self.POLL_BEGIN = {
            "right": ["channel:read:polls", "channel:manage:polls"],
            "payload": {
                "type": TwitchSubscriptionType.POLL_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.POLL_END = {
            "right": ["channel:read:polls", "channel:manage:polls"],
            "payload": {
                "type": TwitchSubscriptionType.POLL_END,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.PREDICTION_BEGIN = {
            "right": ["channel:read:predictions", "channel:manage:predictions"],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_BEGIN,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.PREDICTION_LOCK = {
            "right": ["channel:read:predictions", "channel:manage:predictions"],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_LOCK,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.PREDICTION_END = {
            "right": ["channel:read:predictions", "channel:manage:predictions"],
            "payload": {
                "type": TwitchSubscriptionType.PREDICTION_END,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.VIP_ADD = {
            "right": ["channel:read:vips", "channel:manage:vips"],
            "payload": {
                "type": TwitchSubscriptionType.VIP_ADD,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.VIP_REMOVE = {
            "right": ["channel:read:vips", "channel:manage:vips"],
            "payload": {
                "type": TwitchSubscriptionType.VIP_REMOVE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.STREAM_ONLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_ONLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.STREAM_OFFLINE = {
            "right": [],
            "payload": {
                "type": TwitchSubscriptionType.STREAM_OFFLINE,
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

        self.BITS = {
            "right": ["bits:read"],
            "payload": {
                "type": TwitchSubscriptionType.BITS,
                "version": "beta",
                "condition": {"broadcaster_user_id": broadcaster_user_id}
            }
        }

    def which_right(self, subscription_list: list[str]) -> list[str]:
        rights = []

        for subscription in self.__dict__.values():
            if subscription["payload"]["type"] in subscription_list:
                rights += subscription["right"]

        return list(set(rights))

    def get_subscribe_data(self, subscription_type:str) -> dict[str, str|dict[str, str]]:
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