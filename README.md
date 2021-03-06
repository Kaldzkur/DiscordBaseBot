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
# The token from your discord bot application
DISCORD_TOKEN={YOUR_BOT_TOKEN}
# Your discord ID, being a owner grants you all permissions of bot commands
OWNER_ID={YOUR_DISCORD_ID}
```
Also to use the function of audit log and member join message you need to enable the privileged intents, check the link below for details:
https://discordpy.readthedocs.io/en/latest/intents.html
## Extending the bot for your discord
Creating your own custom bot is fairly easy.
First you fork this project and create a new file for your bot in the root directory.
This file should contain the class of the bot, inheriting from the BaseBot.

````python
import discord
from base_bot import BaseBot, dynamic_prefix

class MyBot(BaseBot):
  pass
  
if __name__ == "__main__":
  import os
  import dotenv
  from base.modules.interactive_help import InteractiveHelpCommand
  import logging.config
  logging.config.fileConfig("logging.conf")
  dotenv.load_dotenv()
  TOKEN = int(os.getenv("DISCORD_TOKEN"))
  OWNER = int(os.getenv("OWNER_ID"))
  #This lookup maps all cog names to a name used in the interactive help.
  cog_categories = {
    "Administration":["Database Commands", "Settings Management Commands", "Administration Commands"],
    "Moderation":["Message Management Commands", "User Management Commands", "Channel Management Commands", "Moderation Commands"],
    "Miscellaneous":["Command Management"]
  }
  intents = discord.Intents.default()
  intents.members = True
  bot = BaseBot(
    command_prefix=dynamic_prefix,
    owner_ids=set([APPA, SIN]),
    case_insensitive = True,
    help_command = InteractiveHelpCommand(cog_categories),
    intents=intents
  )
  bot.run(TOKEN)
````

## Main Features of the base bot
The bot supports different features based on different roles. There exists a role for moderation, one for administration and one for commands.
Most moderation and administrative actions will be logged into text channels.
### Administration
Main administration feature are accessed using a special role. An admin can set the bots' activity.
By default the bot watches a random anime or plays a random game. Its status changes hourly.

`?reboot, ?shutdown, ?upgrade` are commands that use bash shells to reboot/shutdown the python script and optionally pull the newest code from a git repo.
These need to be configured manually: after forking this project, they can be edited to match your needs.
### Database Management
The bot uses many different databases for its features. Each guild will have its own database.
An admin can use a set of commands to manually modify the database of the bot.

Create/delete a table (with multiple primary keys)

Insert/delete a row into a table

Select a row or table from the database

Execute a custom query

for more information use the help command `?help db`.

### Settings
Settings are parameters of the bot which are stored in the table 'bot_settings', admins can access and edit them by command `?settings`. Default settings are settings that are actually referred in the bot's program. Changing a default setting will overwrites the value in database, applies the change in the server if applicable (such as the role/channel names), and affects the commands of the bot. The following default settings are supported:
````text
PREFIX:            command prefix
MAX_WARNINGS:      max allowed warnings
WARN_DURATION:     warning expiry (day)
MUTE_DURATION:     mute expiry (day)
MOD_ROLE_NAME:     gives mod commands
ADMIN_ROLE_NAME:   gives admin commands
BOT_ROLE_NAME:     role the bot claims
CMD_ROLE_NAME:     gives command editing access
MUTE_ROLE_NAME:    revokes posting access
BOT_CATEGORY_NAME: category for logs
NUM_DELETE_CACHE:  num of restorable deleted messages
MODMAIL_EXPIRY:    modmail expiry (min)
AUTO_MODMAIL:      on/off modmail auto deletion
AUTO_UPDATE:       on/off slaps/stats auto update
ERROR_LOG:         on/off error logging
ADMIN_LOG:         on/off admin logging
MOD_LOG:           on/off mod logging
AUDIT_LOG:         on/off audit logging
MESSAGE_LOG:       on/off message logging
ACTIVE_TIME:       interactive message active time
````

If you need to add your own default settings, you can override `initialize_default_settings()` method in the base bot.

### Custom Commands
One of the main features of the bot is that it supports custom commands created by other users.
These commands are stored in a database and loaded when the bot boots up.
This allows many users to customize the bot for your server.
Access to command editing is granted with a special role: Command Master.
An in-depth guide to creating commands can be found in the bots' help. The basic commands are:


`?cmd add name commandtext` will add a command that sends the `commandtext` every time the command is invoked.
A group can be added using `?cmd gadd groupname`. To add a command to that group use `?cmd add "groupname name" commandtext` (the quotes around the group and command are important).
Commands support arguments: if commandtext contains '{}' it will look for an argument when invoked.
For example:

`?cmd add 1up {} received one life.` can be invoked using `?1up arg`.

`?cmd rm name` will remove a command. To remove group all commands attached to that group need to be removed first.

`?cmd edit name newtext` will replace the text of an existing command with `newtext`.


By default a custom command/group also accepts optional arguments including `-d` (for command or group) `-r` (for group only). `-d` will help you delete your original command message if possible, `-r` will invoke a random subcommand in a command group, with all arguments propagated. Usage: `?name -[option] [args]...`.

A command can be specified to have access permissions required, this can be set by `?cmd perm <name> <lv>`. Permission lv1 grants access to all members, lv2 grants access to mods and owners, lv3 grants access to admins and owners, lv4 grants access only to owners.

If you are using the bot on multiple servers, you can also set the commands to be sever-specific or global by `?cmd glob` and `?cmd unglob`. The commands are server-specific by default.

Once a command is finished it can be locked by an admin using `?cmd lock`.
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
This bot automatically send every new member a welcome message and explains the warning system of the bot.
Useful moderation features of the bot are:

`?warn @user reason` lets you add warnings to a user. This will send the user a DM which tells him he received a warning and when it expires.
The `reason` is optional and can be omitted, but if specified the user will be informed of it as well.
If a certain amount of warnings have been accumulated, the user will be kicked. Warnings can be removed with `?warn rm`.

`?kick @user reason` lets you kick a user from the server. Optionally a `reason` can be specified, but it is only for logging purposes.

`?ban @user reason` lets you ban a member from the server. The `reason` is optional and will appear when the ban is viewed.
A user does not have to be in the server for a ban to work. However, if you want to ban a user that has left the server, you need to specify his UID (User ID).

`?mute @user` will mute a user for a set period of time. This will restrict them from posting any messages into any public channel. If the bot has the administrator priviledge it will add the muted role automatically to public channels. Otherwise the muted role has to be added manually.

#### Statistics
The bot automatically tracks statistics of the user. These include but are not limited to:  messages sent, commands sent, reactions made.
Any member of a server can view his own stats with the `?statistics` command.

## Contributing the bot
Contributions are welcome; they will be reviewed before they are merged.
