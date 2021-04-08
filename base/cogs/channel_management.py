from datetime import datetime
import json
import os
import discord
from discord.ext import commands
from base.modules.access_checks import has_mod_role, has_admin_role
from base.modules.constants import CACHE_PATH as path
from base.modules.message_helper import save_message
from base.modules.serializable_object import dump_json, MonitorEntry
import logging

logger = logging.getLogger(__name__)

class ChannelManagementCog(commands.Cog, name="Channel Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    if not os.path.isdir(path):
      os.mkdir(path)
    self.monitor = MonitorEntry.from_json(f"{path}/monitor.json")
    for guild in self.bot.guilds:
      self.init_guild(guild)
    
  def init_guild(self, guild):
    if guild.id not in self.monitor:
      self.monitor[guild.id] = []
  
  def cog_unload(self):
    dump_json(self.monitor, f'{path}/monitor.json')

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.MissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    elif isinstance(error, commands.BotMissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but I do not have permission to execute that command!")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `{context.command.qualified_name}`.")
    elif isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while executing that command.")
      
  @commands.Cog.listener()
  async def on_message(self, message):
    if hasattr(message, "guild") and message.guild:
      if message.guild.id not in self.monitor:
        return
      if message.channel.id in self.monitor[message.guild.id]:
        await save_message(self.bot, message)

  @commands.group(
    name="channel",
    brief="Channel management",
    invoke_without_command=True,
    aliases=["ch"]
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel(self, context):
    await context.send_help("channel")

  @_channel.command(
    name="close",
    brief="Makes Channel invisible",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_close(self, context, members: commands.Greedy[discord.Member] = [], roles: commands.Greedy[discord.Role] = []):
    overwrites = discord.PermissionOverwrite(view_channel = False)
    permissions = context.message.channel.overwrites
    #bot still needs access to the channel
    permissions[context.guild.me] = discord.PermissionOverwrite(
      create_instant_invite=True, manage_channels=True, manage_roles=True, manage_webhooks=True, read_messages=True,
      send_messages=True, send_tts_messages=True, manage_messages=True, embed_links=True, 
      attach_files=True, read_message_history=True, mention_everyone=True, use_external_emojis=True, add_reactions=True
    )
    targets = []
    if len(members) == len(roles) == 0:
      permissions[context.guild.default_role] = overwrites
    else:
      for member in members:
        permissions[member] = overwrites
        targets.append(f"{member.mention}\n{member}")
      for role in roles:
        permissions[role] = overwrites
        targets.append(f"{role.mention}")
    await context.message.channel.edit(overwrites=permissions)
    fields = {
      "Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}",
      "Targets":"\n".join(targets) if targets else None
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="closed a channel",
      fields=fields, timestamp=context.message.created_at
    )

  @_channel.command(
    name="open",
    brief="Makes Channel visible",
    aliases=["unmute"]
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_open(self, context, members: commands.Greedy[discord.Member] = [], roles: commands.Greedy[discord.Role] = []):
    overwrites = discord.PermissionOverwrite(
      create_instant_invite=True, manage_channels=False, manage_roles=False, manage_webhooks=False, read_messages=True,
      send_messages=True, send_tts_messages=True, manage_messages=False, embed_links=True, 
      attach_files=True, read_message_history=True, mention_everyone=True, use_external_emojis=True, add_reactions=True
    )
    permissions = context.message.channel.overwrites
    targets = []
    if context.guild.me in permissions:
      permissions.pop(context.guild.me, None)
    else:
      permissions[context.guild.me] = overwrites
    if len(members) == len(roles) == 0:
      if context.guild.default_role in permissions:
        permissions.pop(context.guild.default_role, None)
      else:
        permissions[context.guild.default_role] = overwrites
    else:
      for member in members:
        if member in permissions:
          if permissions[member] != overwrites:
            permissions.pop(member, None)
        else:
          permissions[member] = overwrites
        targets.append(f"{member.mention}\n{member}")
      for role in roles:
        if role in permissions:
          if permissions[role] != overwrites:
            permissions.pop(role, None)
        else:
          permissions[role] = overwrites
        targets.append(f"{role.mention}")
    await context.message.channel.edit(overwrites=permissions)
    fields = {
      "Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}",
      "Targets":"\n".join(targets) if targets else None
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="opened a channel",
      fields=fields, timestamp=context.message.created_at
    )

  @_channel.command(
    name="mute",
    brief="Disables messaging",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_mute(self, context, members: commands.Greedy[discord.Member] = [], roles: commands.Greedy[discord.Role] = []):
    overwrites = discord.PermissionOverwrite(
      view_channel=True, send_messages=False, send_tts_messages=False, manage_messages=False, embed_links=False, 
      attach_files=False, read_message_history=True, mention_everyone=False, use_external_emojis=True, add_reactions=True
    )
    permissions = context.message.channel.overwrites
    #bot still needs access to the channel
    permissions[context.guild.me] = discord.PermissionOverwrite(
      create_instant_invite=True, manage_channels=True, manage_roles=True, manage_webhooks=True, read_messages=True,
      send_messages=True, send_tts_messages=True, manage_messages=True, embed_links=True, 
      attach_files=True, read_message_history=True, mention_everyone=True, use_external_emojis=True, add_reactions=True
    )
    targets = []
    if len(members) == len(roles) == 0:
      permissions[context.guild.default_role] = overwrites
    else:
      for member in members:
        permissions[member] = overwrites
        targets.append(f"{member.mention}\n{member}")
      for role in roles:
        permissions[role] = overwrites
        targets.append(f"{role.mention}")
    await context.message.channel.edit(overwrites=permissions)
    fields = {
      "Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}",
      "Targets":"\n".join(targets) if targets else None
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="muted a channel",
      fields=fields, timestamp=context.message.created_at
    )
    
  @_channel.group(
    name="monitor",
    brief="Starts monitoring channel",
    help="Starts monitoring the current channel by saving all the coming messages ",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_monitor(self, context):
    if context.message.channel.id in self.monitor[context.guild.id]:
      await context.send("This channel is already under monitor.")
      return
    self.monitor[context.guild.id].append(context.message.channel.id)
    await context.send("Started monitoring this channel.")
    fields = {"Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}"}
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="started channel monitoring",
      fields=fields, timestamp=context.message.created_at
    )
    
  @_channel_monitor.command(
    name="off",
    brief="Stops monitoring channel",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_monitor_off(self, context):
    if context.message.channel.id not in self.monitor[context.guild.id]:
      await context.send("This channel is not under monitor.")
      return
    self.monitor[context.guild.id].remove(context.message.channel.id)
    await context.send("Stopped monitoring this channel.")
    fields = {"Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}"}
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="stopped channel monitoring",
      fields=fields, timestamp=context.message.created_at
    )
    
  @_channel_monitor.command(
    name="list",
    brief="Lists monitored channels",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_monitor_list(self, context):
    if context.guild.id not in self.monitor or not self.monitor[context.guild.id]:
      await context.send("No channel in this guild is under monitor.")
    else:
      channels = [context.guild.get_channel(channel_id) for channel_id in self.monitor[context.guild.id]]
      if not channels:
        await context.send("No channel in this guild is under monitor.")
      else:
        await context.send(f"Monitored channel(s):\n" + "\n".join(channel.mention for channel in channels if channel))

def setup(bot):
  bot.add_cog(ChannelManagementCog(bot))
  logger.info("Added channel management.")
