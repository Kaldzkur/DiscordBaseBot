import discord
import os
import pytz
from datetime import datetime, timedelta
from base.modules.async_timer import BotTimer as Timer
import json
from base.modules.special_bot_methods import special_process_command
from base.modules.constants import CACHE_PATH as path

def json_to_object(filename, convert_method):
  object_dict = {}
  try:
    with open(filename) as f:
      data = json.load(f)
      if isinstance(data, dict):
        for key in data:
          try:
            object_dict[int(key)] = [convert_method(msg) for msg in data[key]]
          except:
            pass
  except:
    pass
  return object_dict
  
class SerializableObject(dict):
  def __init__(self):
    self = dict()
    
  @classmethod
  def from_json(cls, filename):
    return json_to_object(filename, cls.from_dict)
    
  @classmethod
  def from_dict(cls, dic: dict):
    obj = cls(self)
    obj.update(dic)
    return obj

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
    
class MessageSchedule(MessageCache):
  def __init__(self):
    super().__init__()
  
  @classmethod
  async def from_message(cls, msg, channel, schedule, content):
    cache = cls()
    cache["time"] = schedule.timestamp()
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
    cache["content"] = dic["content"]
    cache["author"] = dic["author"]
    cache["channel"] = dic["channel"]
    cache["embed"] = dic["embed"]
    cache["files"] = dic["files"]
    return cache
    
  def set_timer(self, guild, bot, scheduler):
    async def send_reminder():
      message = await self.send_now(guild, bot)
      self.delete_schedule(scheduler) # delete after excuting if case there are files or important messages unsent 
    user = bot.get_user(self["author"])
    channel = guild.get_channel(self['channel'])
    task = (f"Schedule a message by "
      f"{user.mention if user is not None else '@Unknown Member'} to "
      f"{channel.mention if channel is not None else '#Unknown Channel'}")
    self.timer = Timer(bot, guild, task, max(self['time'] - datetime.now().timestamp(), 0), send_reminder)
    
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
      fields = {
        "Forced by":f"{user.mention}\n{user}" if user else None,
        "Author":member.mention if member else 'Unknown Member',
        "Channel":channel.mention if channel else 'Unknown Channel',
        "Content":text[:1021] + '...' if text and len(text) > 1021 else text,
        "Embed size":len(embed_post) if embed_post else None,
        "Files":f"{len(files)} file(s)" if files else None}
      await bot.log_message(guild, "MOD_LOG", user=bot.user, action="sent a scheduled message", fields=fields)
    except:
      pass
    
class CommandSchedule(MessageSchedule):
  def __init__(self):
    super().__init__()
    self["cmd"] = True
    
  @classmethod
  async def from_message(cls, msg, schedule, content):
    cache = cls()
    cache["time"] = schedule.timestamp()
    cache["content"] = content
    cache["author"] = msg.author.id
    cache["channel"] = msg.channel.id
    cache["message"] = msg.id # record the message if to find the old message later
    # no need to get the embed or files of the message
    return cache
    
  def set_timer(self, guild, bot, scheduler):
    async def send_reminder():
      self.delete_schedule(scheduler) # delete before excuting to avoid killing from shutdown/reboot/upgrade
      message = await self.send_now(guild, bot)
    user = bot.get_user(self["author"])
    channel = guild.get_channel(self['channel'])
    task = (f"Schedule a command `{self['content']}` by "
      f"{user.mention if user is not None else '@Unknown Member'} to "
      f"{channel.mention if channel is not None else '#Unknown Channel'}")
    self.timer = Timer(bot, guild, task, max(self['time'] - datetime.now().timestamp(), 0), send_reminder)
    
  async def send_now(self, guild, bot, user=None):
    channel = guild.get_channel(self['channel'])
    message = await channel.fetch_message(self["message"])
    member = message.author
    await special_process_command(bot, message, self["content"])
    try:
      # log the message, even if log is failed, the message will be deleted
      title = f"A scheduled command has been processed"
      fields = {
        "Forced by":f"{user.mention}\n{user}" if user else None,
        "Author":member.mention if member else 'Unknown Member',
        "Channel":channel.mention if channel else 'Unknown Channel',
        "Command":self["content"]
      }
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
      
  
      
