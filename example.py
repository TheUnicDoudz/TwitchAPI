#!/usr/bin/env python3
"""
Example usage of the TwitchAPI Bot framework.

This example shows how to create a complete Twitch bot with:
- Command handling
- Points system
- Automatic responses
- Community event handling
- Proper logging

Author: TheUnicDoudz
"""

import logging
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Optional

from twitchapi.chatbot import ChatBot
from twitchapi.twitchcom import TwitchSubscriptionType
from twitchapi.exception import (
    TwitchAuthorizationFailed,
    TwitchMessageNotSentWarning,
    TwitchEndpointError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class ExampleBot(ChatBot):
    """
    Example Twitch bot with complete features.

    Included features:
    - Activity points system
    - Custom commands
    - Automatic responses
    - Community event handling
    - Command cooldowns
    """

    def __init__(self, *args, **kwargs):
        """Initialize bot with custom data."""
        super().__init__(*args, **kwargs)

        # Activity points system
        self.user_points: Dict[str, int] = {}

        # Command cooldowns (in seconds)
        self.command_cooldowns: Dict[str, datetime] = {}
        self.cooldown_duration = 30  # 30 seconds between commands

        # Stream statistics
        self.stream_start_time: Optional[datetime] = None
        self.message_count = 0
        self.unique_users = set()

        # Custom commands
        self.custom_commands = {
            "!discord": "Join our Discord: https://discord.gg/example",
            "!twitter": "Follow us on Twitter: @example",
            "!youtube": "Subscribe to our YouTube: https://youtube.com/example"
        }

        logger.info("🤖 Bot initialized successfully!")

    def _is_command_on_cooldown(self, user_name: str, command: str) -> bool:
        """
        Check if a command is on cooldown for a user.

        Args:
            user_name: Username
            command: Command to check

        Returns:
            True if on cooldown, False otherwise
        """
        cooldown_key = f"{user_name}:{command}"
        if cooldown_key in self.command_cooldowns:
            time_diff = datetime.now() - self.command_cooldowns[cooldown_key]
            if time_diff.total_seconds() < self.cooldown_duration:
                return True

        # Update cooldown
        self.command_cooldowns[cooldown_key] = datetime.now()
        return False

    def _add_user_points(self, user_name: str, points: int = 1) -> None:
        """
        Add points to a user.

        Args:
            user_name: Username
            points: Number of points to add
        """
        if user_name not in self.user_points:
            self.user_points[user_name] = 0
        self.user_points[user_name] += points

    def _safe_send_message(self, message: str, reply_id: Optional[str] = None) -> bool:
        """
        Send a message safely with error handling.

        Args:
            message: Message to send
            reply_id: ID of message to reply to (optional)

        Returns:
            True if message was sent, False otherwise
        """
        try:
            self.send_message(message, reply_id)
            return True
        except TwitchMessageNotSentWarning as e:
            logger.warning(f"Message not sent: {e}")
            return False
        except TwitchEndpointError as e:
            logger.error(f"API error sending message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            return False

    def receive_message(self, id: str, user_id: str, user_name: str,
                        text: str, cheer: bool, emote: bool,
                        thread_id: str, parent_id: str):
        """
        Process received chat messages.

        Handles commands, awards points, and maintains statistics.
        """
        try:
            # Update statistics
            self.message_count += 1
            self.unique_users.add(user_name)

            # Award points (more points for cheers)
            points_to_add = 3 if cheer else 1
            self._add_user_points(user_name, points_to_add)

            logger.info(f"💬 {user_name}: {text}")

            # Handle commands
            if text.startswith("!"):
                self._handle_command(user_name, text.lower(), id)

            # Automatic responses
            self._handle_auto_responses(user_name, text.lower())

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _handle_command(self, user_name: str, text: str, message_id: str):
        """
        Handle bot commands.

        Args:
            user_name: Username
            text: Command text
            message_id: Original message ID
        """
        command = text.split()[0]

        # Check cooldown
        if self._is_command_on_cooldown(user_name, command):
            return

        # Points system commands
        if command == "!points":
            points = self.user_points.get(user_name, 0)
            self._safe_send_message(
                f"@{user_name}, you have {points} points! 🏆",
                message_id
            )

        elif command == "!top":
            self._handle_top_command()

        # Information commands
        elif command == "!uptime":
            self._handle_uptime_command()

        elif command == "!stats":
            self._handle_stats_command()

        # Utility commands
        elif command == "!time":
            current_time = datetime.now().strftime("%H:%M:%S")
            self._safe_send_message(f"Current time is {current_time} ⏰")

        elif command == "!commands":
            commands_list = "!points, !top, !uptime, !stats, !time"
            if self.custom_commands:
                commands_list += ", " + ", ".join(self.custom_commands.keys())
            self._safe_send_message(f"Available commands: {commands_list}")

        # Custom commands
        elif command in self.custom_commands:
            self._safe_send_message(self.custom_commands[command])

        else:
            # Unknown command - do nothing to avoid spam
            pass

    def _handle_top_command(self):
        """Display top 5 most active users."""
        if not self.user_points:
            self._safe_send_message("No points awarded yet! 📊")
            return

        top_users = sorted(
            self.user_points.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        top_msg = "🏆 Top 5 most active: "
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        for i, (name, points) in enumerate(top_users):
            medal = medals[i] if i < len(medals) else f"{i + 1}."
            top_msg += f"{medal} {name} ({points}pts) "

        self._safe_send_message(top_msg)

    def _handle_uptime_command(self):
        """Display stream duration."""
        if self.stream_start_time:
            uptime = datetime.now() - self.stream_start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            self._safe_send_message(f"⏱️ Stream running for {hours}h{minutes:02d}min")
        else:
            self._safe_send_message("⏱️ Stream duration unknown")

    def _handle_stats_command(self):
        """Display chat statistics."""
        stats_msg = (f"📊 Chat stats: {self.message_count} messages, "
                     f"{len(self.unique_users)} unique users")
        self._safe_send_message(stats_msg)

    def _handle_auto_responses(self, user_name: str, text: str):
        """
        Handle automatic responses based on message content.

        Args:
            user_name: Username
            text: Message text in lowercase
        """
        # Greetings
        greetings = ["hello", "hi", "hey", "good morning", "good evening"]
        if any(greeting in text for greeting in greetings):
            if user_name not in getattr(self, '_greeted_users', set()):
                self._safe_send_message(f"Hello {user_name}! 👋")
                if not hasattr(self, '_greeted_users'):
                    self._greeted_users = set()
                self._greeted_users.add(user_name)

    def new_follow(self, user_id: str, user_name: str):
        """Welcome new followers."""
        try:
            logger.info(f"👥 New follower: {user_name}")
            self._safe_send_message(
                f"Welcome {user_name}! Thanks for the follow! ❤️ "
                f"Feel free to say hello in chat! 💬"
            )

            # Award bonus points for following
            self._add_user_points(user_name, 10)

        except Exception as e:
            logger.error(f"Error processing follow: {e}")

    def new_subscribe(self, user_id: str, user_name: str, tier: str, is_gift: bool):
        """Thank new subscribers."""
        try:
            tier_names = {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3"}
            tier_display = tier_names.get(tier, f"Tier {tier}")

            if is_gift:
                logger.info(f"🎁 Gift subscription {tier_display}: {user_name}")
                self._safe_send_message(
                    f"🎁 Thanks for the {tier_display} gift subscription, {user_name}! "
                    f"That's very generous! 💖"
                )
            else:
                logger.info(f"⭐ New subscriber {tier_display}: {user_name}")
                self._safe_send_message(
                    f"🎉 Thanks for the {tier_display} subscription, {user_name}! "
                    f"Welcome to the family! 👨‍👩‍👧‍👦"
                )

            # Bonus points for subscription
            bonus_points = {"1000": 50, "2000": 100, "3000": 200}
            self._add_user_points(user_name, bonus_points.get(tier, 50))

        except Exception as e:
            logger.error(f"Error processing subscription: {e}")

    def new_resub(self, user_name: str, tier: str, streak: int, total: int,
                  duration: int, message: str):
        """Thank resubscriptions."""
        try:
            logger.info(f"🔄 Resubscription: {user_name} (streak: {streak}, total: {total})")

            response = f"🔄 Thanks for the resubscription {user_name}! "
            if streak > 1:
                response += f"{streak} month streak! 🔥 "
            if total > 12:
                response += f"That's {total} months total! 🎂 "
            if message:
                response += f"Message: {message}"

            self._safe_send_message(response)

            # Bonus points based on streak
            bonus_points = min(streak * 10, 200)  # Max 200 points
            self._add_user_points(user_name, bonus_points)

        except Exception as e:
            logger.error(f"Error processing resubscription: {e}")

    def raid_on_caster(self, source: str, nb_viewers: int):
        """Handle incoming raids."""
        try:
            logger.info(f"🚀 Raid from {source} with {nb_viewers} viewers!")

            # Custom message based on raid size
            if nb_viewers >= 100:
                message = f"🚀 HUGE RAID from {source} with {nb_viewers} raiders! " \
                          f"Welcome everyone! This is incredible! 🎊🎉"
            elif nb_viewers >= 20:
                message = f"🚀 Great raid from {source} with {nb_viewers} raiders! " \
                          f"Thanks so much and welcome! 🎉"
            else:
                message = f"🚀 Thanks for the raid {source}! " \
                          f"Welcome to the {nb_viewers} raiders! 👋"

            self._safe_send_message(message)

        except Exception as e:
            logger.error(f"Error processing raid: {e}")

    def channel_reward(self, user_id: str, user_name: str, reward_name: str):
        """Handle channel point rewards."""
        try:
            logger.info(f"🎁 {user_name} used: {reward_name}")

            reward_lower = reward_name.lower()

            if "hydration" in reward_lower or "water" in reward_lower:
                self._safe_send_message(
                    f"💧 {user_name} reminds to drink water! "
                    f"Stay hydrated everyone! 🚰"
                )
            elif "song" in reward_lower or "music" in reward_lower:
                self._safe_send_message(
                    f"🎵 {user_name} requested a song! "
                    f"What a vibe! 🎶"
                )
            elif "shoutout" in reward_lower:
                self._safe_send_message(
                    f"📢 Shoutout to {user_name}! "
                    f"Thanks for supporting the stream! ❤️"
                )
            else:
                self._safe_send_message(
                    f"🎁 {user_name} used '{reward_name}'! Thanks! ✨"
                )

        except Exception as e:
            logger.error(f"Error processing reward: {e}")

    def stream_online(self, type: str, start_time: str):
        """Notify stream start."""
        try:
            self.stream_start_time = datetime.now()
            logger.info(f"🔴 Stream started! Type: {type}")

            # Reset statistics for new stream
            self.message_count = 0
            self.unique_users.clear()
            if hasattr(self, '_greeted_users'):
                self._greeted_users.clear()

            self._safe_send_message("🔴 Stream has started! Welcome everyone! 🎉")

        except Exception as e:
            logger.error(f"Error processing stream start: {e}")

    def stream_offline(self):
        """Notify stream end."""
        try:
            logger.info("⚫ Stream ended")
            self.stream_start_time = None

        except Exception as e:
            logger.error(f"Error processing stream end: {e}")


def signal_handler(signum, frame):
    """Handle clean bot shutdown."""
    logger.info("🔴 Shutdown signal received, closing bot...")
    if 'bot' in globals():
        try:
            bot.stop_event_server()
        except:
            pass
    sys.exit(0)


def main():
    """Main function to launch the bot."""

    # Configuration - Customize this
    config = {
        "client_id": "YOUR_CLIENT_ID",
        "client_secret": "YOUR_CLIENT_SECRET",
        "bot_name": "your_bot_name",
        "channel_name": "channel_name",
        "subscriptions": [
            TwitchSubscriptionType.MESSAGE,
            TwitchSubscriptionType.FOLLOW,
            TwitchSubscriptionType.SUBSCRIBE,
            TwitchSubscriptionType.RESUB_MESSAGE,
            TwitchSubscriptionType.RAID,
            TwitchSubscriptionType.CHANNEL_POINT_ACTION,
            TwitchSubscriptionType.STREAM_ONLINE,
            TwitchSubscriptionType.STREAM_OFFLINE
        ],
        "store_in_db": True,
        "timeout": 300  # 5 minutes for auth
    }

    # Configuration validation
    if config["client_id"] == "YOUR_CLIENT_ID":
        logger.error("❌ Please configure your CLIENT_ID in the code!")
        return

    if config["client_secret"] == "YOUR_CLIENT_SECRET":
        logger.error("❌ Please configure your CLIENT_SECRET in the code!")
        return

    # Handle signals for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("🚀 Starting Twitch bot...")

        # Create and launch bot
        global bot
        bot = ExampleBot(**config)

        logger.info("✅ Bot started successfully!")
        logger.info("💡 Available commands: !points, !top, !uptime, !stats, !time, !commands")
        logger.info("🔴 Bot is now online. Press Ctrl+C to stop.")

        # Keep program running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    except TwitchAuthorizationFailed as e:
        logger.error(f"❌ Authentication error: {e}")
        logger.error("💡 Check your CLIENT_ID, CLIENT_SECRET and redirect URI")

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")

    finally:
        # Cleanup
        if 'bot' in globals():
            try:
                logger.info("🧹 Cleaning up...")
                bot.stop_event_server()
                logger.info("✅ Bot stopped cleanly")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()