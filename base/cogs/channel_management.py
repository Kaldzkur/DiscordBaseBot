from datetime import datetime
import re
import json
import os
import discord
import asyncio
import typing
from urllib.parse import urlparse
from discord.ext import commands, tasks
from base.modules.access_checks import has_mod_role, has_admin_role
from base.modules.constants import CACHE_PATH as path
from base.modules.message_helper import save_message, naive_time_to_seconds
from base.modules.serializable_object import dump_json, MonitorEntry, SuppressQueueEntry, ChannelWhiteListEntry
import logging

logger = logging.getLogger(__name__)

class ChannelManagementCog(commands.Cog, name="Channel Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    if not os.path.isdir(path):
      os.mkdir(path)
    self.monitor = MonitorEntry.from_json(f"{path}/monitor.json")
    self.white_list = ChannelWhiteListEntry.from_json(f'{path}/white_list.json')
    self.clean_tasks = {}
    for guild in self.bot.guilds:
      self.init_guild(guild)
    
  def init_guild(self, guild):
    if guild.id not in self.monitor:
      self.monitor[guild.id] = []
    if guild.id not in self.white_list:
      self.white_list[guild.id] = {}
    if guild.id not in self.clean_tasks:
      self.start_new_task(guild)
      
  def create_new_task(self, guild):
    @tasks.loop(hours=self.get_media_cycle(guild))
    async def auto_clean():
      if guild not in self.bot.guilds:
        self.end_task(guild)
        return
      await self.clean_media_table(guild)
    #@auto_clean.error
    #async def auto_clean_error(error):
      #pass
    @auto_clean.before_loop
    async def before_auto_clean():
      await self.bot.wait_until_ready()
    return auto_clean
  
  def start_new_task(self, guild, forceStart=False):
    if self.get_media_clean(guild) != "ON" and not forceStart:
      return
    if guild.id not in self.clean_tasks:
      self.clean_tasks[guild.id] = self.create_new_task(guild)
      self.clean_tasks[guild.id].start()
    
  def end_task(self, guild):
    if guild.id in self.clean_tasks:
      task = self.clean_tasks[guild.id]
      self.clean_tasks.pop(guild.id)
      task.cancel()
      
  def change_media_clean(self, state, guild):
    if state == "ON":
      self.start_new_task(guild, True)
    else:
      self.end_task(guild)
      
  def change_media_cycle(self, hours, guild):
    if guild.id in self.clean_tasks:
      self.clean_tasks[guild.id].change_interval(hours=hours)
      
  async def clean_media_table(self, guild):
    try:
      now = datetime.now().timestamp()
      cycle = self.get_media_cycle(guild) * 3600
      self.bot.db[guild.id].query(f"DELETE FROM media WHERE time<={now-cycle}")
      await self.bot.log_message(guild, "MOD_LOG", title="Cleaned media records")
      logger.debug(f"Finished cleaning media table in {guild.name} ({guild.id}).")
    except Exception as error:
      await self.bot.on_task_error("Clean media table", error, guild)
  
  def cog_unload(self):
    dump_json(self.monitor, f'{path}/monitor.json')
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
    await self.update_media_on_message(message)
    
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
    
  def get_media_clean(self, guild):
    return self.bot.get_setting(guild, "MEDIA_CLEAN")
    
  def get_media_cycle(self, guild):
    return self.bot.get_setting(guild, "MEDIA_CYCLE")
    
  def get_media_rate_limit(self, guild):
    return self.bot.get_setting(guild, "MEDIA_RATE_LIMIT")
      
  async def message_save(self, message):
    if message.guild.id not in self.monitor:
      return
    if message.channel.id in self.monitor[message.guild.id]:
      await save_message(self.bot, message)
        
  def channel_in_white_list(self, channel):
    suppress_channel = self.get_suppress_channel(channel.guild)
    guild_white_list = self.white_list[channel.guild.id]
    ch_state = guild_white_list[channel.id] if channel.id in guild_white_list else 0 # >0 means in white list, <0 means in black list
    if (suppress_channel == "ALL_BUT_WHITE" and ch_state > 0) or (suppress_channel == "NONE_BUT_BLACK" and ch_state >= 0):
      return True
    else:
      return False
      
      
  async def update_media_on_message(self, message):
    # ignore channels in white list
    if self.channel_in_white_list(message.channel):
      return
    channel = message.channel
    guild = message.guild
    member = message.author
    # update position of messages before
    self.bot.db[guild.id].query(f"UPDATE media SET pos=pos+1 WHERE cid={channel.id}")
    # insert the new media message
    media = self.filter_media(message)
    if media:
      suppress = 1 if media == message.content else -1
      self.bot.db[guild.id].insert_or_update("media", message.id, naive_time_to_seconds(message.created_at), member.id, channel.id, media, 1, suppress)
    # suppress the messages that meet the criteria
    self.suppress_message(channel)
    # check the rate of media and send alert
    if media:
      await self.media_alert(message)
          
  def suppress_message(self, channel):
    # suppress the messages that meet the criteria
    guild = channel.guild
    if not channel.permissions_for(guild.me).manage_messages:
      return
    mode = self.get_suppress_mode(channel.guild)
    now = datetime.now().timestamp()
    if mode == "DELAY":
      suppress_delay = self.get_suppress_delay(guild) * 60
      where_clause = f"time<={now-suppress_delay}"
    elif mode == "POSITION":
      suppress_position = self.get_suppress_position(guild)
      embed_limit = self.get_suppress_limit(guild)
      where_clause = f"pos>{suppress_position} OR mid IN (SELECT mid from temp ORDER BY pos ASC LIMIT -1 OFFSET {embed_limit})"
    else:
      return
    results = self.bot.db[guild.id].query(f"WITH temp as (SELECT * FROM media WHERE cid={channel.id} AND suppress>0) SELECT mid FROM temp WHERE ({where_clause})")
    if results:
      message_ids = [mid[0] for mid in results]
      for mid in message_ids:
        asyncio.ensure_future(self.suppress_message_based_on_id(channel, mid)) # create task to run in background to avoid time delay
      id_list = ", ".join(str(mid) for mid in message_ids)
      self.bot.db[guild.id].query(f"UPDATE media SET suppress=0 WHERE mid IN ({id_list})")
      
  async def media_alert(self, message):
    channel = message.channel
    guild = message.guild
    member = message.author
    rate_limit = self.get_media_rate_limit(guild)
    member_history = self.get_media_history(guild, member=member, channel=None)
    member_rate = sum(num for _, num in member_history)
    if member_rate > rate_limit:
      fields = {
        "User": f"{member.mention}\n{member}\nUID: {member.id}",
        "Top Used Channels": self.get_history_table(member_history, "channel")
        }
      await self.bot.log_message(guild, "MESSAGE_LOG", 
        title=f"@{member.display_name} reached media rate limit",
        description=f"Number of media messages in the last hour: {member_rate}",
        fields=fields, timestamp=datetime.utcnow())
    channel_history = self.get_media_history(guild, member=None, channel=channel)
    channel_rate = sum(num for _, num in channel_history)
    if channel_rate > rate_limit:
      fields = {
        "Channel": f"{channel.mention}\nCID: {channel.id}",
        "Top Senders": self.get_history_table(channel_history, "user")
        }
      await self.bot.log_message(guild, "MESSAGE_LOG", 
        title=f"#{channel.name} reached media rate limit",
        description=f"Number of media messages in the last hour: {channel_rate}",
        fields=fields, timestamp=datetime.utcnow())
          
    
  def filter_media(self, message):
    links = re.findall(r'(https?://\S+)', message.content)
    media = None
    for link in links:
      if self.need_suppress(link):
        media = link
        break
    else:
      for attachment in message.attachments:
        if attachment.height:
          media = attachment.url
          break
    return media
  
          
  def need_suppress(self, content):
    url = urlparse(content)
    return bool(url.netloc) and ("tenor.com" in url.netloc or "giphy.com" in url.netloc or
                                 url.path.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif')))
                                 
  async def suppress_message_based_on_id(self, channel, mid):
    try:
      message = await channel.fetch_message(mid)
      await message.edit(suppress=True)
    except:
      pass
      
  def get_media_history(self, guild, member=None, channel=None, tspan=3600):
    if not member and not channel:
      return None
    elif member and channel:
      select_clause = f"COUNT(mid) AS num"
      where_clause = f"aid={member.id} and cid={channel.id}"
      group_clause = "NULL"
      row_trans = lambda row: [row[0]]
    elif member:
      select_clause = f"cid, COUNT(mid) AS num"
      where_clause = f"aid={member.id}"
      group_clause = "cid"
      row_trans = lambda row: [guild.get_channel(row[0]), row[1]]
    else:
      select_clause = f"aid, COUNT(mid) AS num"
      where_clause = f"cid={channel.id}"
      group_clause = "aid"
      row_trans = lambda row: [guild.get_member(row[0]), row[1]]
    now = datetime.now().timestamp()
    results = self.bot.db[guild.id].query(f"SELECT {select_clause} FROM media WHERE time>{now-tspan} and ({where_clause}) "
                                          f"GROUP BY {group_clause} ORDER BY num DESC")
    return [row_trans(row) for row in results]
    
  def get_history_table(self, results, tp, limit=10):
    if len(results) > limit:
      results = results[:limit]
    table = [[tp.upper(), "NUM"]]
    if tp == "channel":
      prefix = "#"
    else:
      prefix = ""
    table += [[f"{prefix}{obj}", str(num)] if obj else [f"UNKNOWN", str(num)] for obj, num in results]
    max_len_1 = max(len(item) for item, _ in table)
    max_len_2 = max(len(item) for _, item in table)
    return "\n".join(f"`{obj:<{max_len_1}}  {num:<{max_len_2}}`" for obj, num in table)
    
  @commands.command(
    name="media",
    brief="Checks rate of media message",
    help="Checks rate of media message from a member or in a channel"
  )
  @has_mod_role()
  async def _media(self, context, member:typing.Optional[discord.Member], channel:typing.Optional[discord.TextChannel], hours:float=1.0):
    if not member and not channel:
      member = context.author
    history = self.get_media_history(context.guild, member, channel, hours*3600)
    if not history:
      member_info = f" for {member.mention}" if member else ""
      channel_info = f" in {channel.mention}" if channel else ""
      await context.send(f"There is no media record found{member_info}{channel_info}!")
      return
    total_num = sum(row[-1] for row in history)
    rate = float(total_num)/hours
    if member and channel:
      description = f"From Member: {member.mention}\nIn Channel: {channel.mention}"
      table_title = ""
      history_table = ""
    elif member:
      description = f"From member: {member.mention}"
      table_title = "Top Used Channels"
      history_table = self.get_history_table(history, "channel")
    else:
      description = f"In channel: {channel.mention}"
      table_title = "Top Senders"
      history_table = self.get_history_table(history, "user")
    embed = discord.Embed(title=f"Media history in last {hours} hour(s)",
                          description=f"{description}\nTotal Number: {total_num}\nRate: {rate:.2f} per hour",
                          colour=discord.Colour.green(), timestamp=context.message.created_at)
    if table_title and history_table:
      embed.add_field(name=f"{table_title}:", value=f"{history_table}", inline=False)
    embed.set_footer(text="MEDIA RATE")
    await context.send(embed=embed)
      

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
