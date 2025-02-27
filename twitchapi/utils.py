import threading
import inspect
import ctypes
from collections.abc import Callable


class TwitchEndpoint:
    TWITCH_ENDPOINT = "https://api.twitch.tv/helix/"
    TWITCH_WEBSOCKET_URL = "wss://eventsub.wss.twitch.tv/ws"
    TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"

    USER_ID = "users?login="
    SEND_MESSAGE = "chat/messages"
    EVENTSUB_SUBSCRIPTION = "eventsub/subscriptions"
    GET_CUSTOM_REWARD = "channel_points/custom_rewards?broadcaster_id="


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

        self.FOLLOW = {
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

    STREAM_ONLINE = "stream_online"
    STREAM_OFFLINE = "stream_offline"

    BITS = "bits"


def _async_raise(tid, exctype):
    '''Raises an exception in the threads with id tid'''
    if not inspect.isclass(exctype):
        raise TypeError("Only types can be raised (not instances)")
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid),
                                                     ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # "if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class ThreadWithExc(threading.Thread):
    '''A thread class that supports raising an exception in the thread from
       another thread.
    '''

    def _get_my_tid(self):
        """determines this (self's) thread id

        CAREFUL: this function is executed in the context of the caller
        thread, to get the identity of the thread represented by this
        instance.
        """
        if not self.is_alive():  # Note: self.isAlive() on older version of Python
            raise threading.ThreadError("the thread is not active")

        # do we have it cached?
        if hasattr(self, "_thread_id"):
            return self._thread_id

        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid

        # TODO: in python 2.6, there's a simpler way to do: self.ident

        raise AssertionError("could not determine the thread's id")

    def raise_exc(self, exctype):
        """Raises the given exception type in the context of this thread.

        If the thread is busy in a system call (time.sleep(),
        socket.accept(), ...), the exception is simply ignored.

        If you are sure that your exception should terminate the thread,
        one way to ensure that it works is:

            t = ThreadWithExc( ... )
            ...
            t.raise_exc( SomeException )
            while t.isAlive():
                time.sleep( 0.1 )
                t.raise_exc( SomeException )

        If the exception is to be caught by the thread, you need a way to
        check that your thread has caught it.

        CAREFUL: this function is executed in the context of the
        caller thread, to raise an exception in the context of the
        thread represented by this instance.
        """
        _async_raise(self._get_my_tid(), exctype)


class TriggerMap:

    def __init__(self):
        self.__callbacks = {}

    def add_trigger(self, callback: Callable, trigger_value: str):
        if trigger_value in self.__callbacks:
            raise KeyError(f"There's already a callback react to {trigger_value}!!")
        self.__callbacks[trigger_value] = callback

    def trigger(self, trigger_value: str, param: dict=None):
        if trigger_value not in self.__callbacks:
            raise KeyError(f"There's no callback react to {trigger_value}!!")
        self.__callbacks[trigger_value](**param)
