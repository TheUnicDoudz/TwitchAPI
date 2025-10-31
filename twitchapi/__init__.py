"""
TwitchAPI Bot Framework

Une bibliothèque Python robuste pour créer des bots Twitch utilisant l'API Twitch et EventSub.

Modules principaux:
- auth: Gestion de l'authentification OAuth2
- chatbot: Classe principale pour créer des bots
- eventsub: Gestion des événements WebSocket
- db: Gestion de la base de données SQLite
- twitchcom: Constantes et utilitaires pour l'API Twitch
- utils: Utilitaires généraux
- exception: Exceptions personnalisées

Auteur: Votre nom
Version: 1.2.0
Remerciements: Quadricopter (https://github.com/Quadricopter) pour son aide sur OAuth2
"""

from .auth import AuthServer
from .chatbot import ChatBot
from .eventsub import EventSub
from .db import DataBaseManager, DataBaseTemplate
from .twitchcom import (
    TwitchEndpoint,
    TwitchRightType,
    TwitchSubscriptionType,
    TwitchSubscriptionModel,
    TriggerSignal
)
from .utils import ThreadWithExc, TriggerMap
from .exception import (
    TwitchAuthorizationFailed,
    TwitchAuthentificationError,
    TwitchEndpointError,
    TwitchMessageNotSentWarning,
    TwitchEventSubError,
    KillThreadException
)

__version__ = "1.2.0"
__author__ = "Votre nom"
__license__ = "MIT"
__copyright__ = "Copyright 2024"

# Exports principaux
__all__ = [
    # Classes principales
    "AuthServer",
    "ChatBot",
    "EventSub",
    "DataBaseManager",

    # Utilitaires
    "ThreadWithExc",
    "TriggerMap",
    "DataBaseTemplate",

    # Constantes Twitch
    "TwitchEndpoint",
    "TwitchRightType",
    "TwitchSubscriptionType",
    "TwitchSubscriptionModel",
    "TriggerSignal",

    # Exceptions
    "TwitchAuthorizationFailed",
    "TwitchAuthentificationError",
    "TwitchEndpointError",
    "TwitchMessageNotSentWarning",
    "TwitchEventSubError",
    "KillThreadException"
]


def get_version():
    """Retourne la version du framework."""
    return __version__


def get_supported_events():
    """Retourne la liste des événements supportés."""
    return [
        TwitchSubscriptionType.MESSAGE,
        TwitchSubscriptionType.FOLLOW,
        TwitchSubscriptionType.BAN,
        TwitchSubscriptionType.UNBAN,
        TwitchSubscriptionType.SUBSCRIBE,
        TwitchSubscriptionType.SUBSCRIBE_END,
        TwitchSubscriptionType.SUBGIFT,
        TwitchSubscriptionType.RESUB_MESSAGE,
        TwitchSubscriptionType.RAID,
        TwitchSubscriptionType.CHANNEL_POINT_ACTION,
        TwitchSubscriptionType.CHANNEL_CHEER,
        TwitchSubscriptionType.POLL_BEGIN,
        TwitchSubscriptionType.POLL_END,
        TwitchSubscriptionType.PREDICTION_BEGIN,
        TwitchSubscriptionType.PREDICTION_LOCK,
        TwitchSubscriptionType.PREDICTION_END,
        TwitchSubscriptionType.VIP_ADD,
        TwitchSubscriptionType.VIP_REMOVE,
        TwitchSubscriptionType.STREAM_ONLINE,
        TwitchSubscriptionType.STREAM_OFFLINE,
        TwitchSubscriptionType.BITS
    ]