# 🚀 Quick Start Guide

Create your first Twitch bot in 5 minutes!

## ⚡ Express Installation

```bash
# 1. Clone the project
git clone https://github.com/your-name/twitch-api-bot
cd twitch-api-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy configuration
cp config.example.py config.py
```

## 🔑 Minimal Configuration

Edit `config.py` and modify these 4 lines:

```python
CLIENT_ID = "your_twitch_client_id"
CLIENT_SECRET = "your_twitch_client_secret"
BOT_NAME = "your_bot_account_name"
CHANNEL_NAME = "channel_name_to_monitor"
```

### 📋 Get Your Twitch Credentials

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Click "Register Your Application"
3. **Name**: `My Twitch Bot`
4. **OAuth Redirect URLs**: `http://localhost:8000/oauth2callback`
5. **Category**: `Chat Bot`
6. Note your **Client ID** and **Client Secret**

## 🤖 First Bot

Create `my_bot.py`:

```python
from config import get_config
from twitchapi import ChatBot, TwitchSubscriptionType

class MyFirstBot(ChatBot):
    def receive_message(self, id, user_id, user_name, text, cheer, emote, thread_id, parent_id):
        print(f"💬 {user_name}: {text}")
        
        if text.startswith("!hello"):
            self.send_message(f"Hello {user_name}! 👋")
    
    def new_follow(self, user_id, user_name):
        print(f"👥 New follower: {user_name}")
        self.send_message(f"Thanks for the follow {user_name}! ❤️")

# Launch bot
if __name__ == "__main__":
    config = get_config()
    config["subscriptions"] = [
        TwitchSubscriptionType.MESSAGE,
        TwitchSubscriptionType.FOLLOW
    ]
    
    bot = MyFirstBot(**config)
    print("🤖 Bot started! Press Ctrl+C to stop.")
    input()
    bot.stop_event_server()
```

## ▶️ Launch

```bash
python my_bot.py
```

1. 🌐 A web page will open automatically
2. 🔐 Log in to Twitch
3. ✅ Authorize the application
4. 🎉 Your bot is online!

## 🎯 Quick Test

In Twitch chat, type:
- `!hello` → Bot responds
- Follow the channel → Bot thanks you

## 🔧 Express Troubleshooting

### ❌ "CLIENT_ID must be configured"
- Check that you modified `config.py`
- CLIENT_ID and CLIENT_SECRET should not contain "your_"

### ❌ "Authentication error"
- Verify your Twitch credentials
- Redirect URI must be exactly: `http://localhost:8000/oauth2callback`

### ❌ "Port already in use"
- Change `OAUTH_PORT = 8001` in `config.py`
- Update URI in Twitch Developer Console

### ❌ Bot doesn't respond to messages
- Check that BOT_NAME matches your connected account
- Make sure bot is in the channel chat

## 📚 Next Steps

1. **More commands**: Add `if` statements in `receive_message()`
2. **More events**: Add `TwitchSubscriptionType.SUBSCRIBE`, etc.
3. **Database**: Enable `store_in_db=True`
4. **Complete example**: Look at `example_bot.py`

## 🆘 Quick Help

- **Complete documentation**: `README.md`
- **Advanced example**: `example_bot.py`
- **Detailed configuration**: `config.example.py`
- **GitHub Issues**: [Report a problem](https://github.com/TheUnicDoudz/TwitchAPI/issues)

---

**🎉 Congratulations! Your Twitch bot is working!** 

Now customize it according to your needs!