# DiscordBaseBot
This is a basic general purpose bot for discord using discord.py api.
It supports many features, including but not limited to a moderation suite.

## Installation
You need a few PyPI packages for this bot to work:

````bash
pip install -U discord.py
pip install -U python-dotenv
pip install -U pytz
pip install -U emoji
pip install -U python-dateutil
````
And you also need a .env file to specify all environment parameters:
```text
DISCORD_TOKEN={YOUR_BOT_TOKEN}
OWNER_ID={YOUR_DISCORD_ID}
```
## Extending the bot for your discord
Creating your own custom bot is fairly easy.
First you fork this project and create a new file for your bot in the root directory.
This file should contain the class of the bot, inheriting from the BaseBot.

````python
import discord
from base_bot import BaseBot

class MyBot(BaseBot):
  pass
  
if __name__ == "__main__":
  import os
  import dotenv
  from base.modules.interactive_help import InteractiveHelpCommand
  dotenv.load_dotenv()
  TOKEN = os.getenv("DISCORD_TOKEN")
  OWNER = os.getenv("OWNER_ID")
  #This lookup maps all cog names to a name used in the interactive help.
  cog_categories = {
    "Administration":["Database Commands", "Settings Management Commands", "Administration Commands"],
    "Moderation":["Message Management Commands", "User Management Commands", "Channel Management Commands", "Moderation Commands"],
    "Miscellaneous":["Command Management"]
  }
  bot = MyBot(
    command_prefix="?",
    owner_ids=set([OWNER]),
    case_insensitive = True,
    help_command = InteractiveHelpCommand(cog_categories)
  )
  bot.run(TOKEN)
````

## Main Features
### Administration
#### Set the activity of the bot
#### Shutdown, reboot, upgrade
#### ID lookup, invite link
#### Logging of all admin/mod/error activities
### Database Management
#### Create/delete table, insert/delete row, select, general query
#### Database backup
### Settings
#### Default settings
#### Add/edit/remove/reset settings
### Custom Commands
#### Add/edit/remove custom commands (groups)
#### Lock/globalize custom commands
### Channel Management
#### Channel mute/unmute/open/close
#### Channel monitor
### Secrete Channels
#### Create/close secrete channels
#### Auto-delete, keep-alive
### Message Management
#### Bulk delete, bulk move, announce, edit, react
#### Schedule messages, commands
#### Storage in database
### User Management
#### Welcome message
#### Warn, kick, ban, mute, prune
#### Statisctics tracking

## Contributing the bot
Contributions are welcome; they will be reviewed before they are merged.
