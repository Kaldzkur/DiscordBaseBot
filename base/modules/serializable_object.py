import discord
import os
import pytz
import time
from datetime import datetime, timedelta
from base.modules.async_timer import BotTimer as Timer
import json
from base.modules.special_bot_methods import special_process_command
from base.modules.constants import CACHE_PATH as path
import logging

logger = logging.getLogger(__name__)

def json_to_object(filename, convert_method):
    data = {}
    try:
      with open(filename) as f:
        data = convert_method(json.load(f))
    except Exception as e:
      logger.error(f"{filename} ignored because of {e.__class__.__name__}: {e}")
    return data

def dict_json_to_object(filename, convert_method):
  def full_convert_method(data):
    assert isinstance(data, dict)
    object_dict = {}
    for key in data:
      try:
        object_dict[int(key)] = convert_method(data[key])
      except Exception as e:
        logger.warning(f"{e.__class__.__name__} ignored while loading {filename}: {e}")
    return object_dict
  return json_to_object(filename, full_convert_method)
  
def dump_json(data, filename):
  try:
    with open(filename, 'w') as f:
      json.dump(data, f)
  except Exception as e:
    logger.error(f"{e.__class__.__name__} ignored while dumping to {filename}: {e}")
    
    
class JsonEntry:

  @classmethod
  def from_json(cls, filename):
    return json_to_object(filename, cls.from_data)
  
  @classmethod
  def from_data(cls, data):
    return data
  
  
  
class GuildEntry:

  @classmethod
  def from_json(cls, filename):
    return dict_json_to_object(filename, cls.from_data)
  
  @classmethod
  def from_data(cls, data):
    return data
    

class SuppressQueueEntry(GuildEntry):
  
  @classmethod
  def from_data(cls, data):
    assert isinstance(data, dict)
    result = {}
    for key in data:
      assert isinstance(data[key], list)
      new_list = []
      result[int(key)] = new_list
      for element in data[key]:
        assert isinstance(element, list) and len(element) == 2 and isinstance(element[1], int) and element[1] > 0
        new_list.append(element)
      new_list.sort(reverse=True, key=lambda element: element[1])
    return result
    

class MonitorEntry(GuildEntry):
  
  @classmethod
  def from_data(cls, data):
    assert isinstance(data, list)
    return data
    

class RoleLinksEntry(GuildEntry):
  
  @classmethod
  def from_data(cls, data):
    assert isinstance(data, list)
    for link in data:
      assert("role" in link and "channel" in link and "emoji" in link and ("mod_role" in link or "message" in link))
    return data
  
  
class SerializableObject(dict):
  def __init__(self):
    self = dict()
    
  @classmethod
  def from_json(cls, filename):
    convert_method = lambda data: [cls.from_dict(msg) for msg in data]
    return dict_json_to_object(filename, convert_method)
    
  @classmethod
  def from_dict(cls, dic: dict):
    obj = cls(self)
    obj.update(dic)
    return obj
    
  def to_string(self, context):
    return str(self)

class MessageCache(SerializableObject):
  def __init__(self):
    self["time"] = -1
    self["content"] = ""
    self["author"] = None
    self["channel"] = None
    self["embed"] = None
    self["files"] = []
  
  @classmethod
  async def from_message(cls, msg: discord.Message):
    cache = cls()
    cache["time"] = pytz.utc.localize(msg.created_at).timestamp()
    cache["content"] = msg.content
    cache["author"] = msg.author.id
    cache["channel"] = msg.channel.id
    # get the embed
    for embed in msg.embeds:
      if len(embed) > 0:
        cache["embed"] = embed.to_dict()
        break
    # get all files attached
    for attachment in msg.attachments:
      try:
        await attachment.save(f"{path}/{attachment.id}_{attachment.filename}")
        cache["files"].append(f"{attachment.id}_{attachment.filename}")
      except:
        pass
    return cache
  
  @classmethod
  def from_dict(cls, dic: dict):
    cache = cls()
    cache["time"] = dic["time"]
    cache["content"] = dic["content"]
    cache["author"] = dic["author"]
    cache["channel"] = dic["channel"]
    cache["embed"] = dic["embed"]
    cache["files"] = dic["files"]
    return cache
    
  def del_files(self):
    for file_name in self["files"]:
      try:
        os.remove(f"{path}/{file_name}")
      except:
        pass
    self["files"].clear()
    
  def get_files(self):
    files = []
    for file_name in self["files"]:
      if os.path.isfile(f"{path}/{file_name}"):
        files.append(discord.File(f"{path}/{file_name}", filename=file_name.split("_", 1)[-1]))
    return files
    
  def get_embed(self):
    try:
      return discord.Embed.from_dict(self["embed"])
    except:
      return None
    
  def restore_content(self, context):
    member = context.bot.get_user(self["author"])
    old_message = self["content"]
    content = old_message.replace('\n> ', '\n').replace('\n', '\n> ')
    origin_channel = context.guild.get_channel(self['channel'])
    if content:
      content = f"{member.mention if member is not None else 'Unkown Member'} said in {origin_channel.mention if origin_channel is not None else 'Unkown Channel'}:\n> {content}"
    else:
      content = f"{member.mention if member is not None else 'Unkown Member'} said in {origin_channel.mention if origin_channel is not None else 'Unkown Channel'}:"
    return (content, self.get_embed(), self.get_files())
    
  async def restore(self, context):
    (content, embed_post, files) = self.restore_content(context)
    await context.send(content=content, embed=embed_post, files=files)
    self.del_files()
  
  def __lt__(self, other):
    return self["time"] < other["time"]
    
  def to_string(self, context):
    channel = context.guild.get_channel(self['channel'])
    member = context.bot.get_user(self['author'])
    msg = (
      f"Channel: {channel.mention if channel is not None else 'Unknown Channel'}\n"
      f"Author: {member.mention if member is not None else 'Unknown Member'}\n"
      f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(self['time']))} UTC\n"
    )
    if self['content']:
      msg += f"Content length: {len(self['content'])}\n"
    if self['embed'] is not None:
      msg += f"Embed size: {len(discord.Embed.from_dict(self['embed']))}\n"
    if len(self['files']) > 0:
      msg += f"Files: {len(self['files'])} file(s)\n"
    return msg
    
class MessageSchedule(MessageCache):
  def __init__(self):
    super().__init__()
  
  @classmethod
  async def from_message(cls, msg, channel, schedule, content, repeat_interval=None):
    cache = cls()
    cache["time"] = schedule.timestamp()
    cache["repeat_interval"] = repeat_interval.total_seconds() if repeat_interval else None
    cache["content"] = content
    cache["author"] = msg.author.id
    cache["channel"] = channel.id
    # get the embed
    for embed in msg.embeds:
      if len(embed) > 0:
        cache["embed"] = embed.to_dict()
        break
    # get all files attached
    for attachment in msg.attachments:
      try:
        await attachment.save(f"{path}/{attachment.id}_{attachment.filename}")
        cache["files"].append(f"{attachment.id}_{attachment.filename}")
      except:
        pass
    return cache
    
  @classmethod
  def from_dict(cls, dic: dict):
    if "cmd" in dic and dic["cmd"]:
      cache = CommandSchedule()
      cache["message"] = dic["message"]
    else:
      cache = cls()
    cache["time"] = dic["time"]
    cache["repeat_interval"] = dic["repeat_interval"]
    cache["content"] = dic["content"]
    cache["author"] = dic["author"]
    cache["channel"] = dic["channel"]
    cache["embed"] = dic["embed"]
    cache["files"] = dic["files"]
    return cache
    
  def set_timer(self, guild, bot, scheduler):
    async def send_reminder():
      message = await self.send_now(guild, bot)
      if not self["repeat_interval"]: # only delete if it do not need repeating
        self.delete_schedule(scheduler) # delete after excuting if case there are files or important messages unsent 
      else:
        self.set_timer(guild, bot, scheduler)
    user = bot.get_user(self["author"])
    channel = guild.get_channel(self['channel'])
    task = (f"Schedule a message by "
      f"{user.mention if user is not None else '@Unknown Member'} to "
      f"{channel.mention if channel is not None else '#Unknown Channel'}")
    now = datetime.now().timestamp()
    if self["repeat_interval"]: # need to repeat, scheduled at the next repeating time
      while self["time"] < now:
        self['time'] += self["repeat_interval"]
    time = max(self["time"] - now, 0)
    self.timer = Timer(bot, guild, task, time, send_reminder)
    
  def cancel(self):
    try:
      self.timer.cancel()
      return True
    except:
      return False
      
  def delete_schedule(self, scheduler):
    self.del_files()
    try:
      scheduler.remove(self)
    except:
      pass
      
  async def send_now(self, guild, bot, user=None):
    channel = guild.get_channel(self['channel'])
    member = guild.get_member(self["author"])
    embed_post = self.get_embed()
    files = self.get_files()
    if not self['content'] and embed_post is None and len(files) == 0:
      text = f"{member.mention if member is not None else '@Unknown Member'} Here is a reminder that your scheduled time has arrived."
    else:
      text = self['content']
    await channel.send(content=text, embed=embed_post, files=files)
    try:
      # log the message, even if log is failed, the message will be deleted
      title = f"A scheduled message has been sent"
      fields = {}
      if user:
        fields["Forced by"] = f"{user.mention}\n{user}\nUID: {user.id}"
      if member:
        fields["Author"] = f"{member.mention}\n{member}\nUID: {member.id}"
      if channel:
        fields["Channel"] = f"{channel.mention}\nCID: {channel.id}"
      if text and len(text) > 1021:
        fields["Content"] = text[:1021] + '...'
      else:
        fields["Content"] = text
      if embed_post:
        fields["Embed size"] = len(embed_post)
      if files:
        fields["Files"] = f"{len(files)} file(s)"
      await bot.log_message(guild, "MOD_LOG", user=bot.user, action="sent a scheduled message", fields=fields)
    except:
      pass
      
  def to_string(self, context):
    channel = context.guild.get_channel(self['channel'])
    member = context.bot.get_user(self['author'])
    msg = (
      f"Author: {member.mention if member is not None else 'Unknown Member'}\n"
      f"To be Sent in: {channel.mention if channel is not None else 'Unknown Channel'}\n"
      f"Scheduled at: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(self['time']))} UTC\n"
    )
    if self["repeat_interval"]:
      msg += f"Repeat every: {str(timedelta(seconds=self['repeat_interval']))}\n"
    if "cmd" in self and self["cmd"]:
      msg += f"Command: {self['content']}\n"
    elif self['content']:
      msg += f"Content length: {len(self['content'])}\n"
    if self['embed'] is not None:
      msg += f"Embed size: {len(discord.Embed.from_dict(self['embed']))}\n"
    if len(self['files']) > 0:
      msg += f"Files: {len(self['files'])} file(s)\n"
    return msg
    
class CommandSchedule(MessageSchedule):
  def __init__(self):
    super().__init__()
    self["cmd"] = True
    
  @classmethod
  async def from_message(cls, msg, schedule, content, repeat_interval=None):
    cache = cls()
    cache["time"] = schedule.timestamp()
    cache["repeat_interval"] = repeat_interval.total_seconds() if repeat_interval else None
    cache["content"] = content
    cache["author"] = msg.author.id
    cache["channel"] = msg.channel.id
    cache["message"] = msg.id # record the message if to find the old message later
    # no need to get the embed or files of the message
    return cache
    
  def set_timer(self, guild, bot, scheduler):
    async def send_reminder():
      if not self["repeat_interval"]: # only delete if it do not need repeating
        self.delete_schedule(scheduler) # delete before excuting to avoid killing from shutdown/reboot/upgrade
      else:
        self.set_timer(guild, bot, scheduler)
      message = await self.send_now(guild, bot)
    user = bot.get_user(self["author"])
    channel = guild.get_channel(self['channel'])
    task = (f"Schedule a command `{self['content']}` by "
      f"{user.mention if user is not None else '@Unknown Member'} to "
      f"{channel.mention if channel is not None else '#Unknown Channel'}")
    now = datetime.now().timestamp()
    if self["repeat_interval"]: # need to repeat, scheduled at the next repeating time
      while self["time"] < now:
        self['time'] += self["repeat_interval"]
    time = max(self["time"] - now, 0)
    self.timer = Timer(bot, guild, task, time, send_reminder)
    
  async def send_now(self, guild, bot, user=None):
    channel = guild.get_channel(self['channel'])
    message = await channel.fetch_message(self["message"])
    member = message.author
    await special_process_command(bot, message, self["content"])
    try:
      # log the message, even if log is failed, the message will be deleted
      title = f"A scheduled command has been processed"
      fields = {}
      if user:
        fields["Forced by"] = f"{user.mention}\n{user}\nUID: {user.id}"
      if member:
        fields["Author"] = f"{member.mention}\n{member}\nUID: {member.id}"
      if channel:
        fields["Channel"] = f"{channel.mention}\nCID: {channel.id}"
      fields["Command"] = self["content"]
      await bot.log_message(guild, "MOD_LOG", user=bot.user, action="processed a scheduled command", fields=fields)
    except:
      pass
      
class SecretChannelEntry(SerializableObject):
  def __init__(self, user=None, channel=None):
    if user is not None:
      self["user"] = user.id
    else:
      self["user"] = None
    if channel is not None:
      self["channel"] = channel.id
    else:
      self["channel"] = None
    self["alive"] = False
  
  @classmethod
  def from_dict(cls, dic: dict):
    entry = cls()
    entry["user"] = dic["user"]
    entry["channel"] = dic["channel"]
    entry["alive"] = dic["alive"]
    return entry
    
  async def set_auto_delete(self, guild, cog):
    channel = guild.get_channel(self["channel"])
    user = cog.bot.get_user(self["user"])
    user_mention = user.mention if user is not None else '@Unknown Member'
    if channel is not None and not self["alive"]:
      last_msg = None
      async for message in channel.history(limit=1):
        last_msg = message
        break
      if last_msg is None:
        active_time = channel.created_at
      else:
        active_time = last_msg.created_at
      current_time = datetime.utcnow()
      expiry = cog.get_expiry(guild)
      if active_time + timedelta(minutes=expiry) <= current_time:
        # expired
        hint_content = (f"Hey {user_mention}, don't forget to close the channel if it is not needed anymore. "
          f"If no more messages are sent within the next {expiry} minutes, this channel will be closed automatically.\n"
          f"Send `{cog.bot.get_guild_prefix(guild)}modmail alive` to prevent this channel from closing.")
        if last_msg is not None and last_msg.author.id == cog.bot.user.id and last_msg.content == hint_content:
          # delete the channel
          await cog.delete_secret_channel(channel, user, "Auto deleted because of no activity")
        else:
          # send the hint and set the timer
          await channel.send(hint_content)
          self.timer = Timer(cog.bot, guild, f"Auto Delete Modmail Channel {channel.mention} for {user_mention}", 60*expiry, self.set_auto_delete, guild, cog)
      else:
        # not expired, set a new timer
        dtime = active_time + timedelta(minutes=expiry) - current_time
        self.timer = Timer(cog.bot, guild, f"Auto Delete Modmail Channel {channel.mention} for {user_mention}", dtime.total_seconds(), self.set_auto_delete, guild, cog)
    return channel
    
  def cancel(self):
    try:
      self.timer.cancel()
      return True
    except:
      return False
      
  
      
