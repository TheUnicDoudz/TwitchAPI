# TwitchAPI Bot Framework

A robust Python library for creating Twitch bots using the Twitch API and EventSub WebSocket.

## 🎯 Features

- **Complete OAuth2 authentication** with automatic token management
- **EventSub WebSocket** for real-time event reception
- **SQLite database** for storing event history
- **Robust error handling** and automatic reconnection
- **Simple API** for creating custom bots
- **Full support** for Twitch events (messages, follows, subs, raids, etc.)

## 📋 Prerequisites

- Python 3.8+
- A Twitch Developer application (Client ID and Client Secret)
- Required Python modules (see `requirements.txt`)

## 🚀 Installation

```bash
git clone https://github.com/TheUnicDoudz/TwitchAPI.git
cd twitch-api-bot
pip install -r requirements.txt
```

## ⚙️ Configuration

### 1. Create a Twitch Application

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Create a new application
3. Note your **Client ID** and **Client Secret**
4. Configure the redirect URI: `http://localhost:8000/oauth2callback`

### 2. Bot Configuration

```python
from twitchapi.chatbot import ChatBot
from twitchapi.twitchcom import TwitchSubscriptionType

# Basic configuration
CLIENT_ID = "your_client_id"
CLIENT_SECRET = "your_client_secret" 
BOT_NAME = "your_bot_name"
CHANNEL_NAME = "channel_name"

# Events to listen for
SUBSCRIPTIONS = [
    TwitchSubscriptionType.MESSAGE,
    TwitchSubscriptionType.FOLLOW,
    TwitchSubscriptionType.SUBSCRIBE,
    TwitchSubscriptionType.RAID
]

# Create bot
bot = ChatBot(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    bot_name=BOT_NAME,
    channel_name=CHANNEL_NAME,
    subscriptions=SUBSCRIPTIONS,
    store_in_db=True  # To save to database
)
```

## 🤖 Usage Example

### Basic bot with automatic responses

```python
from twitchapi.chatbot import ChatBot
from twitchapi.twitchcom import TwitchSubscriptionType
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

class MyBot(ChatBot):
    """Custom Twitch bot with basic features."""
    
    def receive_message(self, id: str, user_id: str, user_name: str, 
                       text: str, cheer: bool, emote: bool, 
                       thread_id: str, parent_id: str):
        """Process chat messages."""
        print(f"💬 {user_name}: {text}")
        
        # Bot commands
        if text.startswith("!hello"):
            self.send_message(f"Hello {user_name}! 👋")
            
        elif text.startswith("!time"):
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M:%S")
            self.send_message(f"Current time is {current_time} ⏰")
    
    def new_follow(self, user_id: str, user_name: str):
        """Welcome new followers."""
        print(f"👥 New follower: {user_name}")
        self.send_message(f"Thanks for the follow {user_name}! ❤️")
    
    def new_subscribe(self, user_id: str, user_name: str, tier: str, is_gift: bool):
        """Thank new subscribers."""
        tier_name = {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3"}
        tier_display = tier_name.get(tier, tier)
        
        if is_gift:
            print(f"🎁 Gift subscription {tier_display}: {user_name}")
        else:
            print(f"⭐ New subscriber {tier_display}: {user_name}")
            self.send_message(f"Thanks for subscribing {user_name}! 🎉")
    
    def raid_on_caster(self, source: str, nb_viewers: int):
        """Handle incoming raids."""
        print(f"🚀 Raid from {source} with {nb_viewers} viewers!")
        self.send_message(f"Thanks for the raid {source}! "
                         f"Welcome to the {nb_viewers} raiders! 🎊")

# Launch bot
if __name__ == "__main__":
    bot = MyBot(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        bot_name="bot_name",
        channel_name="channel_name",
        subscriptions=[
            TwitchSubscriptionType.MESSAGE,
            TwitchSubscriptionType.FOLLOW,
            TwitchSubscriptionType.SUBSCRIBE,
            TwitchSubscriptionType.RAID
        ],
        store_in_db=True
    )
    
    try:
        print("🤖 Bot started! Press Ctrl+C to stop.")
        input()  # Keep program running
    except KeyboardInterrupt:
        print("\n🔴 Stopping bot...")
        bot.stop_event_server()
```

### Advanced bot with commands

```python
class AdvancedBot(ChatBot):
    """Bot with advanced features."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_points = {}  # Simple points system
    
    def receive_message(self, id: str, user_id: str, user_name: str, 
                       text: str, cheer: bool, emote: bool, 
                       thread_id: str, parent_id: str):
        """Advanced message handling."""
        
        # Award points for participation
        if user_name not in self.user_points:
            self.user_points[user_name] = 0
        self.user_points[user_name] += 1
        
        # Commands
        if text.startswith("!points"):
            points = self.user_points.get(user_name, 0)
            self.send_message(f"{user_name}, you have {points} points! 🏆")
            
        elif text.startswith("!top"):
            # Top 3 most active users
            top_users = sorted(self.user_points.items(), 
                             key=lambda x: x[1], reverse=True)[:3]
            
            if top_users:
                top_msg = "🥇 Top 3: "
                for i, (name, pts) in enumerate(top_users, 1):
                    top_msg += f"{i}. {name} ({pts}pts) "
                self.send_message(top_msg)
                
        elif text.startswith("!uptime"):
            # Here you could calculate stream uptime
            self.send_message("Stream started 2h30min ago! ⏱️")
    
    def channel_reward(self, user_id: str, user_name: str, reward_name: str):
        """Handle channel point rewards."""
        print(f"🎁 {user_name} used: {reward_name}")
        
        if "hydration" in reward_name.lower():
            self.send_message(f"{user_name} reminds the streamer to drink! 💧")
        elif "song" in reward_name.lower():
            self.send_message(f"🎵 Song request from {user_name}!")
```

## 📊 Database

The framework can automatically save all events to an SQLite database:

```python
# Enable database
bot = ChatBot(
    # ... other parameters
    store_in_db=True,
    # db_path="path/to/my_database.db"  # Optional
)

# Direct database access
from twitchapi.db import DataBaseManager

db = DataBaseManager("path/to/database.db")
# Use custom SQL queries
db.execute_script("SELECT * FROM message WHERE user = 'username'")
```

### Database Structure

The database contains several tables:
- `message`: Chat messages
- `follow`: New followers
- `subscribe`: Subscriptions
- `reward`: Channel point rewards
- `raid`: Incoming/outgoing raids
- `poll`: Polls
- `prediction`: Predictions
- And more...

## 🔧 Error Handling

The framework includes robust error handling:

```python
from twitchapi.exception import (
    TwitchAuthorizationFailed,
    TwitchAuthentificationError,
    TwitchEndpointError,
    TwitchMessageNotSentWarning
)

try:
    bot.send_message("Hello chat!")
except TwitchMessageNotSentWarning as e:
    print(f"Message not sent: {e}")
except TwitchEndpointError as e:
    print(f"API error: {e}")
```

## 📈 Supported Events

### Messages and interactions
- `MESSAGE`: Chat messages
- `CHANNEL_CHEER`: Cheers/Bits
- `CHANNEL_POINT_ACTION`: Channel point rewards

### Community
- `FOLLOW`: New followers
- `SUBSCRIBE`: New subscriptions
- `SUBSCRIBE_END`: Subscription ends
- `SUBGIFT`: Gift subscriptions
- `RESUB_MESSAGE`: Resubscriptions
- `RAID`: Raids

### Moderation
- `BAN`: Bans
- `UNBAN`: Unbans
- `VIP_ADD`: VIP additions
- `VIP_REMOVE`: VIP removals

### Stream
- `STREAM_ONLINE`: Stream online
- `STREAM_OFFLINE`: Stream offline

### Interactions
- `POLL_BEGIN`: Poll start
- `POLL_END`: Poll end
- `PREDICTION_BEGIN`: Prediction start
- `PREDICTION_LOCK`: Prediction lock
- `PREDICTION_END`: Prediction end

## 🔒 Security

### Token Management
- Tokens are automatically renewed
- Secure local storage
- Authentication error handling

### Permissions
```python
from twitchapi.twitchcom import TwitchRightType

# Custom permissions
custom_permissions = [
    TwitchRightType.USER_WRITE_CHAT,
    TwitchRightType.MODERATOR_READ_FOLLOWERS,
    TwitchRightType.CHANNEL_READ_SUBSCRIPTIONS
]

bot = ChatBot(
    # ... other parameters
    right=custom_permissions  # Specific permissions
)
```

## 🐛 Debugging

### Enable detailed logging
```python
import logging

# Configure logging for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

### Connection test
```python
# Simple authentication test
from twitchapi.auth import AuthServer

auth = AuthServer()
try:
    auth.authentication(
        client_id="your_id",
        client_secret="your_secret",
        scope=["user:read:chat"]
    )
    print("✅ Authentication successful!")
except Exception as e:
    print(f"❌ Error: {e}")
```

## 📚 API Reference

### ChatBot Class

#### Main methods
- `send_message(message, reply_id=None)`: Send a message
- `ban_user(username, reason, duration=None)`: Ban a user
- `get_follower()`: Get followers list
- `get_subscriber()`: Get subscribers list
- `stop_event_server()`: Stop event server

#### Callbacks to override
All event methods can be overridden in your class:
- `receive_message(...)` 
- `new_follow(...)`
- `new_subscribe(...)`
- `channel_reward(...)`
- And all other events...

## 🤝 Contributing

Contributions are welcome! Here's how to contribute:

1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Code Standards
- Follow PEP 8 conventions
- Add docstrings for all functions
- Include tests for new features
- Use type hints

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## 🙏 Acknowledgments

- **[Quadricopter](https://github.com/Quadricopter)** for invaluable help with OAuth2 implementation
- The Twitch community for API documentation
- All contributors who helped improve this project

## 📞 Support

- **GitHub Issues**: [Create an issue](https://github.com/TheUnicDoudz/TwitchAPI/issues)
- **Twitch Documentation**: [Twitch API](https://dev.twitch.tv/docs/api/)
- **EventSub**: [EventSub Documentation](https://dev.twitch.tv/docs/eventsub/)

---

**Made with ❤️ for the Twitch community**