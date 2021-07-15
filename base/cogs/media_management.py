from datetime import datetime
import re
import os
import discord
import asyncio
import typing
import json
from urllib.parse import urlparse
from discord.ext import commands, tasks
from base.modules.access_checks import has_mod_role, check_channel_permissions
from base.modules.constants import CACHE_PATH as path
from base.modules.message_helper import naive_time_to_seconds
from base.modules.serializable_object import dump_json, ChannelWhiteListEntry
import logging

logger = logging.getLogger(__name__)

def isPrivateChannel(channel):
  # check whether the channel is private in a guild
  channel_permission = channel.overwrites_for(channel.guild.default_role)
  return channel_permission.read_messages == False or channel_permission.send_messages == False

class MediaManagementCog(commands.Cog, name="Media Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    if not os.path.isdir(path):
      os.mkdir(path)
    self.white_list = ChannelWhiteListEntry.from_json(f'{path}/white_list.json')
    self.clean_tasks = {}
    self.alert_cd = {}
    for guild in self.bot.guilds:
      self.init_guild(guild)
    
  def init_guild(self, guild):
    if guild.id not in self.white_list:
      self.white_list[guild.id] = {}
    if guild.id not in self.clean_tasks:
      self.start_new_task(guild)
    if guild.id not in self.alert_cd:
      self.alert_cd[guild.id] = {}
      
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
      cycle = self.get_media_cycle(guild)
      tbegin = now - cycle * 3600
      self.bot.db[guild.id].query(f"DELETE FROM media WHERE time<={tbegin} AND suppress<=0")
      logger.debug(f"Finished cleaning media table in {guild.name} ({guild.id}).")
      # show details of records during the last cycle
      user_history, channel_history = self.get_media_history(guild, tbegin=tbegin)
      if not user_history:
        await self.bot.log_message(guild, "MESSAGE_LOG", title="Cleaned media records")
        return
      total_num = sum(row[-1] for row in user_history)
      rate = float(total_num)/cycle
      fields = {"Top Used Channels": self.get_history_table(channel_history, "channel"),
                "Top Senders": self.get_history_table(user_history, "user")}
      await self.bot.log_message(guild, "MESSAGE_LOG", title="Cleaned media records",
                                 description=f"**Media history in last {cycle} hour(s):**\nTotal Number: {total_num}\nRate: {rate:.2f} per hour",
                                 fields=fields)
    except Exception as error:
      await self.bot.on_task_error("Clean media table", error, guild)
  
  def cog_unload(self):
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
    await self.update_media_on_message(message)
    
  def get_suppress_mode(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_MODE")
    
  def get_suppress_filter(self, guild):
    return self.bot.get_setting(guild, "SUPPRESS_FILTER")
    
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
    
  def get_media_alert_cd(self, guild):
    return self.bot.get_setting(guild, "MEDIA_ALERT_CD")
        
  def channel_in_white_list(self, channel):
    suppress_channel = self.get_suppress_channel(channel.guild)
    guild_white_list = self.white_list[channel.guild.id]
    ch_state = guild_white_list[channel.id] if channel.id in guild_white_list else 0 # >0 means in white list, <0 means in black list
    if ch_state > 0:
      return True
    if ch_state < 0:
      return False
    if isPrivateChannel(channel): # don't filter private channel generally
      return True
    # the remaining cases are non-private channels which are not in either white or black list, filter it only if the mode is "ALL_BUT_WHITE"
    if suppress_channel == "ALL_BUT_WHITE":
      return False
    else:
      return True
      
  async def update_media_on_message(self, message):
    if self.get_suppress_mode(message.guild) == "OFF":
      return
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
      suppress = 1 if self.need_suppress(message) else -1
      self.bot.db[guild.id].insert_or_update("media", message.id, naive_time_to_seconds(message.created_at), member.id, channel.id, json.dumps(media), 1, suppress)
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
    suppress_delay = self.get_suppress_delay(guild) * 60
    where_clause_delay = f"time<={now-suppress_delay}"
    suppress_position = self.get_suppress_position(guild)
    embed_limit = self.get_suppress_limit(guild)
    where_clause_position = f"pos>{suppress_position} OR mid IN (SELECT mid from temp ORDER BY pos ASC LIMIT -1 OFFSET {embed_limit})"
    if mode == "DELAY":
      where_clause = where_clause_delay
    elif mode == "POSITION":
      where_clause = where_clause_position
    elif mode == "ANY":
      where_clause = f"({where_clause_delay}) OR ({where_clause_position})"
    elif mode == "BOTH":
      where_clause = f"({where_clause_delay}) AND ({where_clause_position})"
    else:
      return
    results = self.bot.db[guild.id].query(f"WITH temp as (SELECT * FROM media WHERE cid={channel.id} AND suppress>0) SELECT mid FROM temp WHERE {where_clause}")
    if results:
      message_ids = [mid[0] for mid in results]
      for mid in message_ids:
        asyncio.ensure_future(self.suppress_message_based_on_id(channel, mid)) # create task to run in background to avoid time delay
      id_list = ", ".join(str(mid) for mid in message_ids)
      self.bot.db[guild.id].query(f"UPDATE media SET suppress=0 WHERE mid IN ({id_list})")
      
  async def media_alert(self, message):
    guild = message.guild
    alert_cd = self.get_media_alert_cd(guild) * 60
    tnow = datetime.now().timestamp()
    if alert_cd < 0: # no alert settings
      return
    channel = message.channel
    member = message.author
    rate_limit = self.get_media_rate_limit(guild)
    
    # member alert
    if member.id not in self.alert_cd[guild.id] or self.alert_cd[guild.id][member.id] + alert_cd < tnow:
      member_history = self.get_media_history(guild, member=member, channel=None, tbegin=tnow-3600)
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
        self.alert_cd[guild.id][member.id] = tnow
    
    # channel alert
    if channel.id not in self.alert_cd[guild.id] or self.alert_cd[guild.id][channel.id] + alert_cd < tnow:
      channel_history = self.get_media_history(guild, member=None, channel=channel, tbegin=tnow-3600)
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
        self.alert_cd[guild.id][channel.id] = tnow
          
    
  def filter_media(self, message):
    media = []
    if not message.author.bot:
      for embed in message.embeds:
        if embed.url:
          media.append(embed.url)
      for attachment in message.attachments:
        if attachment.height:
          media.append(attachment.url)
    return media
  
          
  def need_suppress(self, message):
    sfilter = self.get_suppress_filter(message.guild)
    if sfilter == "HEAVY":
      if len(message.embeds) > 0  and len(message.attachments) == 0:
        return True
    elif sfilter == "MEDIUM":
      if len(message.embeds) > 0  and len(message.attachments) == 0:
        for embed in message.embeds:
          if embed.url:
            if self.is_suppress_link(embed.url):
              return True
    elif sfilter == "LIGHT":
      if len(message.embeds) == 1 and len(message.attachments) == 0 and message.embeds[0].url == message.content:
        return self.is_suppress_link(message.content)
    return False
    
  def is_suppress_link(self, link):
    url = urlparse(link)
    return bool(url.netloc) and ("tenor.com" in url.netloc or "giphy.com" in url.netloc or
                                 url.path.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif')))
                                 
  async def suppress_message_based_on_id(self, channel, mid):
    try:
      message = await channel.fetch_message(mid)
      await message.edit(suppress=True)
    except:
      pass
      
  def get_media_history(self, guild, member=None, channel=None, tbegin=0):
    if not member and not channel:
      result1 = self.bot.db[guild.id].query(f"SELECT aid, COUNT(mid) AS num FROM media WHERE time>{tbegin} "
                                            f"GROUP BY aid ORDER BY num DESC")
      if not result1:
        return [], [] # don't need to send the second query if there is no data
      user_history = [[guild.get_member(aid), num] for aid, num in result1]
      result2 = self.bot.db[guild.id].query(f"SELECT cid, COUNT(mid) AS num FROM media WHERE time>{tbegin} "
                                            f"GROUP BY cid ORDER BY num DESC")
      channel_history = [[guild.get_channel(cid), num] for cid, num in result2]
      return user_history, channel_history
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
    results = self.bot.db[guild.id].query(f"SELECT {select_clause} FROM media WHERE time>{tbegin} and ({where_clause}) "
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
    return "\n".join(f"`{num:<{max_len_2}}  {obj:<{max_len_1}}`" for obj, num in table)
    
  @commands.group(
    name="media",
    brief="Checks rate of media message",
    help="Checks rate of media message from a member or in a channel",
    invoke_without_command=True,
  )
  @has_mod_role()
  async def _media(self, context, member:typing.Optional[discord.Member], channel:typing.Optional[discord.TextChannel], hours:float=1.0):
    history = self.get_media_history(context.guild, member, channel, datetime.now().timestamp()-hours*3600)
    if not history or (isinstance(history, tuple) and not history[0]):
      member_info = f" for {member.mention}" if member else ""
      channel_info = f" in {channel.mention}" if channel else ""
      await context.send(f"There is no media record found in last {hours} hour(s){member_info}{channel_info}!")
      return
    if member and channel:
      description = f"From Member: {member.mention}\nIn Channel: {channel.mention}\n"
      history_table = {}
      total_num = history[0][-1]
    elif member:
      description = f"From member: {member.mention}\n"
      history_table = {"Top Used Channels": self.get_history_table(history, "channel")}
      total_num = sum(row[-1] for row in history)
    elif channel:
      description = f"In channel: {channel.mention}\n"
      history_table = {"Top Senders": self.get_history_table(history, "user")}
      total_num = sum(row[-1] for row in history)
    else:
      description = ""
      user_history, channel_history = history
      history_table = {"Top Used Channels": self.get_history_table(channel_history, "channel"),
                       "Top Senders": self.get_history_table(user_history, "user")}
      total_num = sum(row[-1] for row in user_history)
    rate = float(total_num)/hours
    embed = discord.Embed(title=f"Media history in last {hours} hour(s)",
                          description=f"{description}Total Number: {total_num}\nRate: {rate:.2f} per hour",
                          colour=discord.Colour.green(), timestamp=context.message.created_at)
    for table_title, table_content in history_table.items():
      embed.add_field(name=f"{table_title}:", value=f"{table_content}", inline=False)
    embed.set_footer(text="MEDIA RATE")
    await context.send(embed=embed)
      
  @_media.command(
    name="suppress",
    brief="Suppress the messages' embeds",
    help="Suppress the embeds of n messages from member(s) in a channel with skipping m messages, if member is not specified it will suppress any message, if channel is not specified it will search the current channel.",
    usage="[@mentions]... [#channel] [number=1] [skip_num=0]",
    aliases=["sup", "remove", "rm"]
  )
  @commands.has_permissions(read_messages=True, read_message_history=True, manage_messages=True)
  @commands.bot_has_permissions(read_messages=True, read_message_history=True, manage_messages=True)
  @has_mod_role()
  async def _media_suppress(self, context, members:commands.Greedy[discord.Member], channel:typing.Optional[discord.TextChannel], num:typing.Optional[int]=1, skip_num:typing.Optional[int]=0):
    if num <= 0:
      raise commands.UserInputError("num must be a positive number.")
    if channel is None:
      channel = context.channel
    elif channel != context.channel:
      check_channel_permissions(channel, context.author, ["read_messages", "read_message_history", "manage_messages"])
    msg_count = 0
    suppressed = 0
    async for message in channel.history():
      if suppressed >= num:
        break
      if message.id == context.message.id:
        continue # skip the command
      if len(members) == 0 or message.author in members:
        msg_count += 1
        if msg_count > skip_num: # skip the first m messages
          if message.embeds:
            await message.edit(suppress=True)
          suppressed += 1
    fields = {
      "Author(s)":"\n".join([f"{member.mention}\n{member}\nUID: {member.id}" for member in members]) if members else None,
      "Channel":f"{channel.mention}\nCID: {channel.id}",
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action=f"suppressed embed(s) of {suppressed} message(s)",
      fields=fields, timestamp=context.message.created_at
    )
    if suppressed == 0:
      await send_temp_message(context, "Could not suppress message(s).", 10)
    await context.message.delete()
    
  @_media.command(
    name="unsuppress",
    brief="Unsuppress the messages' embeds",
    help="Unsuppress the embeds of n messages from member(s) in a channel with skipping m messages, if member is not specified it will unsuppress any message, if channel is not specified it will search the current channel.",
    usage="[@mentions]... [#channel] [number=1] [skip_num=0]",
    aliases=["unsup", "recover", "rec"]
  )
  @commands.has_permissions(read_messages=True, read_message_history=True, manage_messages=True)
  @commands.bot_has_permissions(read_messages=True, read_message_history=True, manage_messages=True)
  @has_mod_role()
  async def _media_unsuppress(self, context, members:commands.Greedy[discord.Member], channel:typing.Optional[discord.TextChannel], num:typing.Optional[int]=1, skip_num:typing.Optional[int]=0):
    if num <= 0:
      raise commands.UserInputError("num must be a positive number.")
    if channel is None:
      channel = context.channel
    elif channel != context.channel:
      check_channel_permissions(channel, context.author, ["read_messages", "read_message_history", "manage_messages"])
    msg_count = 0
    unsuppressed = 0
    async for message in channel.history():
      if unsuppressed >= num:
        break
      if message.id == context.message.id:
        continue # skip the command
      if len(members) == 0 or message.author in members:
        msg_count += 1
        if msg_count > skip_num: # skip the first m messages
          await message.edit(suppress=False)
          unsuppressed += 1
    fields = {
      "Author(s)":"\n".join([f"{member.mention}\n{member}\nUID: {member.id}" for member in members]) if members else None,
      "Channel":f"{channel.mention}\nCID: {channel.id}",
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action=f"unsuppressed embed(s) of {unsuppressed} message(s)",
      fields=fields, timestamp=context.message.created_at
    )
    if unsuppressed == 0:
      await send_temp_message(context, "Could not unsuppress message(s).", 10)
    await context.message.delete()
   
  @_media.group(
    name="white",
    brief="Adds channel to white list",
    help="Adds the current channel to white list so that link embeds are always ignored here",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _media_white(self, context):
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
    
  @_media_white.command(
    name="list",
    brief="Shows channel white/black list",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _media_white_list(self, context):
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
    
  @_media.group(
    name="black",
    brief="Adds channel to black list",
    help="Adds the current channel to black list so that link embeds are always suppressed here",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _media_black(self, context):
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
  @_media_black.command(
    name="list",
    brief="Shows channel white/black list",
  )
  @commands.has_permissions(manage_channels=True)
  @commands.bot_has_permissions(manage_channels=True)
  @has_mod_role()
  async def _media_black_list(self, context):
    await context.invoke(self._media_white_list)

def setup(bot):
  bot.add_cog(MediaManagementCog(bot))
  logger.info("Added media management.")
