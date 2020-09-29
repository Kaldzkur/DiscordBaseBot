import os
import time
import discord
import typing
from discord.ext import commands
from base.modules.access_checks import has_admin_role

class AdminCog(commands.Cog, name="Administration Commands"):
  def __init__(self, bot):
    self.bot = bot

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command.")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `{context.prefix}{context.command.qualified_name}`.")
    elif isinstance(error, commands.MaxConcurrencyReached):
      await context.send(f"Sorry {context.author.mention}, but only {error.number} user(s) can execute `{context.prefix}{context.command.qualified_name}` at the same time!")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened...")

  @commands.group(
    name="activity",
    brief="Sets bot activity",
    case_insensitive = True,
    invoke_without_command=True
  )
  @has_admin_role()
  async def _activity(self, context):
    await context.send_help("activity")

  @_activity.command(
    name="play",
    brief="Bot status to Playing",
  )
  @has_admin_role()
  async def _activity_play(self, context, *, _name):
    await self.bot.change_presence(activity=discord.Game(name=_name))
    fields = {
      "Type":"Playing",
      "Name":_name
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="set bot activity", fields=fields,
      timestamp=context.message.created_at
    )

  @_activity.command(
    name="watch",
    brief="Bot status to Watching",
  )
  @has_admin_role()
  async def _activity_watch(self, context, *, _name):
    await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=_name))
    fields = {
      "Type":"Watching",
      "Name":_name
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="set bot activity", fields=fields,
      timestamp=context.message.created_at
    )

  @_activity.command(
    name="listen",
    brief="Bot status to Listening",
  )
  @has_admin_role()
  async def _activity_listen(self, context, *, _name):
    await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=_name))
    fields = {
      "Type":"Listening",
      "Name":_name
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="set bot activity", fields=fields,
      timestamp=context.message.created_at
    )

  @commands.command(
    name="leave",
    brief="Deletes bot-related stuff",
  )
  @commands.max_concurrency(1)
  @commands.is_owner()
  async def _leave(self, context):
    await context.send(f"> Deleting bot-specific channels and roles...")
    await self.bot.delete_logs(context.guild)
    await self.bot.delete_roles(context.guild)
    await context.guild.leave()

  @commands.command(
    name="nick",
    brief="Changes or views bot nick",
  )
  @commands.is_owner()
  async def _nick(self, context, nick=None):
    if nick is not None:
      await context.guild.me.edit(nick=nick)
      await self.bot.log_message(context.guild, "ADMIN_LOG", 
        user=context.author, action="changed nickname", target=self.bot.user,
        fields={"Name":nick}, timestamp=context.message.created_at
      )
    await context.send(f"```Nick: {context.guild.me.nick}```")

  @commands.command(
    name="upgrade",
    brief="Upgrades codebase",
  )
  @commands.max_concurrency(1)
  @commands.is_owner()
  async def _upgrade(self, context):
    await context.send(f"> Starting upgrade of codebase...")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="was upgraded", target=self.bot.user,
      timestamp=context.message.created_at
    )
    await self.bot.close()
    os.system("sh upgrade.sh")

  @commands.command(
    name="reboot",
    brief="Reboots bot",
  )
  @commands.max_concurrency(1)
  @commands.is_owner()
  async def _reboot(self, context):
    await context.send(f"> Rebooting...")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="was rebooted", target=self.bot.user,
      timestamp=context.message.created_at
    )
    await self.bot.close()
    os.system("sh reboot.sh")

  @commands.command(
    name="shutdown",
    brief="Shuts down bot",
  )
  @commands.max_concurrency(1)
  @commands.is_owner()
  async def _shutdown(self, context):
    await context.send(f"> Signing off...")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="was shut down", target=self.bot.user,
      timestamp=context.message.created_at
    )
    await self.bot.close()
    os.system("sh shutdown.sh")

  @commands.command(
    name="id",
    brief="Shows id of user(s)",
    help="Shows id of user(s)/role(s)/channel(s)",
    usage="[@mention/#channel]..."
  )
  @has_admin_role()
  async def _id(self, context, items:commands.Greedy[typing.Union[discord.User,discord.Role,discord.TextChannel]]):
    if len(items) == 0:
      await context.send_help("id")
      return
    await context.send("\n".join([f"{item} ({item.id})" for item in items]))

  @commands.group(
    name="owner",
    brief="Shows server/bot owner(s)",
    invoke_without_command=True
  )
  async def _owner(self, context):
    await context.send_help("owner")

  @_owner.command(
    name="server",
    brief="Shows server owner",
  )
  async def _server_owner(self, context):
    await context.send(f"Server Owner:\n{context.guild.owner.mention} ({context.guild.owner})")

  @_owner.command(
    name="bot",
    brief="Shows bot owner(s)",
  )
  async def _bot_owner(self, context):
    owners = []
    for id in self.bot.owner_ids:
      owner = discord.utils.get(context.guild.members, id=id)
      if owner is not None: 
        owners.append(owner)
    owner_string = "\n".join([f"{owner.mention} ({owner})" for owner in owners])
    await context.send(f"Bot Owner(s):\n{owner_string}")

  @commands.command(
    name="invite",
    brief="Link to invite bot",
  )
  async def _invite_link(self, context):
    embed = discord.Embed(title=f"Invite {self.bot.user.name}",
                          #url=f"https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=1544027223&scope=bot",
                          url=f"https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot", #administrator
                          description="You want to invite me to your server? Click on the link above!")
    await context.send(content=None, embed=embed)

#This function is needed for the load_extension routine.
def setup(bot):
  bot.add_cog(AdminCog(bot))
  print("Added administration cog.")
