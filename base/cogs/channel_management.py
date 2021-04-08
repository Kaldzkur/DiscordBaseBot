from datetime import datetime
import json
import os
import discord
import asyncio
from urllib.parse import urlparse
from discord.ext import commands
from base.modules.access_checks import has_mod_role, has_admin_role
from base.modules.constants import CACHE_PATH as path
from base.modules.message_helper import save_message
from base.modules.serializable_object import dump_json, MonitorEntry, SuppressQueueEntry, ChannelWhiteListEntry
import logging

logger = logging.getLogger(__name__)

class ChannelManagementCog(commands.Cog, name="Channel Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    if not os.path.isdir(path):
      os.mkdir(path)
    self.monitor = MonitorEntry.from_json(f"{path}/monitor.json")
    self.suppress_queue = SuppressQueueEntry.from_json(f'{path}/suppress_queue.json')
    self.white_list = ChannelWhiteListEntry.from_json(f'{path}/white_list.json')
    for guild in self.bot.guilds:
      self.init_guild(guild)
    
  def init_guild(self, guild):
    if guild.id not in self.monitor:
      self.monitor[guild.id] = []
    if guild.id not in self.suppress_queue:
      self.suppress_queue[guild.id] = {}
    if guild.id not in self.white_list:
      self.white_list[guild.id] = {}
  
  def cog_unload(self):
    dump_json(self.monitor, f'{path}/monitor.json')
    dump_json(self.suppress_queue, f'{path}/suppress_queue.json')
    dump_json(self.white_list, f'{path}/white_list.json')

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
    if not message.guild:
      return
    await self.message_save(message)
    await self.message_suppress(message)
    
  def get_suppress_mode(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_MODE")
    
  def get_suppress_delay(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_DELAY")
    
  def get_suppress_position(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_POSITION")
    
  def get_suppress_limit(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_LIMIT")
    
  def get_suppress_channel(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_CHANNEL")
      
  async def message_save(self, message):
    if message.guild.id not in self.monitor:
      return
    if message.channel.id in self.monitor[message.guild.id]:
      await save_message(self.bot, message)
    
        
  async def message_suppress(self, message):
    # this will suppress the embed (usually a gif) of a message if the content is a pure link
    if self.channel_in_white_list(message.channel):
      return
    if message.channel.permissions_for(message.guild.me).manage_messages:
      mode = self.get_suppress_mode(message.guild)
      if mode == "DELAY":
        await self.message_suppress_on_delay(message)
      elif mode == "POSITION":
        await self.message_suppress_on_position(message)
        
  def channel_in_white_list(self, channel):
    suppress_channel = self.get_suppress_channel(channel.guild)
    guild_white_list = self.white_list[channel.guild.id]
    ch_state = guild_white_list[channel.id] if channel.id in guild_white_list else 0 # >0 means in white list, <0 means in black list
    if (suppress_channel == "ALL_BUT_WHITE" and ch_state > 0) or (suppress_channel == "NONE_BUT_BLACK" and ch_state >= 0):
      return True
    else:
      return False
    
  async def message_suppress_on_delay(self, message):
    suppress_delay = self.get_suppress_delay(message.guild)
    if self.need_suppress(message.content):
      await asyncio.sleep(suppress_delay*60)
      try:
        await message.edit(suppress=True)
      except:
        pass
    
  async def message_suppress_on_position(self, message):
    suppress_position = self.get_suppress_position(message.guild)
    embed_limit = self.get_suppress_limit(message.guild)
    if message.channel.id not in self.suppress_queue[message.guild.id]:
      self.suppress_queue[message.guild.id][message.channel.id] = []
    message_list = self.suppress_queue[message.guild.id][message.channel.id]
    for message_info in message_list:
      message_info[1] += 1
    if self.need_suppress(message.content):
      message_list.append([message.id, 1])
    while message_list and (message_list[0][1] > suppress_position or len(message_list) > embed_limit):
      message_info = message_list.pop(0)
      try:
        suppress_message = await message.channel.fetch_message(message_info[0])
        await suppress_message.edit(suppress=True)
      except:
        pass
          
  def need_suppress(self, content):
    url = urlparse(content)
    return bool(url.netloc)
     

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
    help="Starts monitoring the current channel by saving all the coming messages.",
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
    if not self.monitor[context.guild.id]:
      await context.send("No channel in this guild is under monitor.")
    else:
      channels = [context.guild.get_channel(channel_id) for channel_id in self.monitor[context.guild.id]]
      if not channels:
        await context.send("No channel in this guild is under monitor.")
      else:
        await context.send(f"Monitored channel(s):\n" + "\n".join(channel.mention for channel in channels if channel))
        
  @_channel.group(
    name="white",
    brief="Adds channel to white list",
    help="Adds the current channel to white list so that link embeds are always ignored here",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_white(self, context):
    if context.message.channel.id not in self.white_list[context.guild.id]:
      self.white_list[context.guild.id][context.message.channel.id] = 0
    state = self.white_list[context.guild.id][context.message.channel.id]
    if state > 0:
      await context.send("This channel is already in white list.")
      return
    elif state == 0:
      self.white_list[context.guild.id][context.message.channel.id] = 1
      action = "put channel in white list"
      await context.send("This channel is put in the white list.")
    else:
      self.white_list[context.guild.id][context.message.channel.id] = 0
      action = "remove channel from black list"
      await context.send("This channel is removed from black list.")
    fields = {"Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}"}
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action=action,
      fields=fields, timestamp=context.message.created_at
    )
    
  @_channel_white.command(
    name="list",
    brief="Shows channel white/black list",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_white_list(self, context):
    white_list = []
    black_list = []
    for channel_id, state in self.white_list[context.guild.id].items():
      channel = context.guild.get_channel(channel_id)
      if channel:
        if state > 0:
          white_list.append(channel)
        elif state < 0:
          black_list.append(channel)
    if not white_list and not black_list:
      await context.send("White/black list is empty in this server.")
    else:
      white_list = "\n".join([channel.mention for channel in white_list]) if white_list else "None"
      black_list = "\n".join([channel.mention for channel in black_list]) if black_list else "None"
      await context.send(f"White list:\n{white_list}\n\nBlack list:\n{black_list}")
    
  @_channel.group(
    name="black",
    brief="Adds channel to black list",
    help="Adds the current channel to black list so that link embeds are always suppressed here",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_black(self, context):
    if context.message.channel.id not in self.white_list[context.guild.id]:
      self.white_list[context.guild.id][context.message.channel.id] = 0
    state = self.white_list[context.guild.id][context.message.channel.id]
    if state < 0:
      await context.send("This channel is already in black list.")
      return
    elif state == 0:
      self.white_list[context.guild.id][context.message.channel.id] = -1
      action = "put channel in black list"
      await context.send("This channel is put in the black list.")
    else:
      self.white_list[context.guild.id][context.message.channel.id] = 0
      action = "remove channel from white list"
      await context.send("This channel is removed from white list.")
    fields = {"Channel":f"{context.message.channel.mention}\nCID: {context.message.channel.id}"}
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action=action,
      fields=fields, timestamp=context.message.created_at
    )
  @_channel_black.command(
    name="list",
    brief="Shows channel white/black list",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _channel_black_list(self, context):
    await context.invoke(self._channel_white_list)

def setup(bot):
  bot.add_cog(ChannelManagementCog(bot))
  logger.info("Added channel management.")
