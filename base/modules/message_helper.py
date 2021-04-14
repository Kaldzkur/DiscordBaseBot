import time
import pytz
import asyncio
import json
import os
import inspect
import discord
from discord.ext import commands
from base.modules.constants import num_emojis, CACHE_PATH as path

def json_load_list(string):
  if string:
    try:
      result = json.loads(string)
      if not isinstance(result, list):
        result = []
    except:
      result = []
  else:
    result = []
  return result

async def get_message_attachments(message):
  # get the first embed if any
  embedOrigin = None
  for embed in message.embeds:
    if len(embed) > 0:
      embedOrigin = embed
      break
  # get all files attached
  files = []
  for attachment in message.attachments:
    files.append(await attachment.to_file())
  return (embedOrigin, files)
  
def naive_time_to_seconds(date):
  return pytz.utc.localize(date).timestamp()
  
def seconds_to_date_string(seconds):
  return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(seconds))
  
async def message_to_row(message):
  embeds = json.dumps([embed.to_dict() for embed in message.embeds])
  filenames = []
  for attachment in message.attachments:
    try:
      await attachment.save(f"{path}/{attachment.id}_{attachment.filename}")
      filenames.append(f"{attachment.id}_{attachment.filename}")
    except:
      pass
  files = json.dumps(filenames)
  return (message.id, naive_time_to_seconds(message.created_at), message.author.id,
    message.channel.id, message.content, embeds, files)
    
def get_message_from_row(row, bot, guild):
  if isinstance(row, dict):
    row = row.values()
  mid, ctime, aid, cid, content, embeds, files = row
  ctime = seconds_to_date_string(ctime)
  author = guild.get_member(aid)
  author = author.mention if author else f"Unknown ID {aid}"
  channel = guild.get_channel(cid)
  channel = channel.mention if channel else f"Unknown ID {cid}"
  embeds = json_load_list(embeds)
  files = json_load_list(files)
  return mid, ctime, author, channel, content, embeds, files
  
def get_message_brief(row, bot, guild):
  mid, ctime, author, channel, content, embeds, files = get_message_from_row(row, bot, guild)
  text = (f"Message ID: {mid}\n"
          f"Time: {ctime} UTC\n"
          f"Author: {author}\n"
          f"Channel: {channel}")
  if content:
    text += f"\nContent length: {len(content)}"
  if embeds:
    text += f"\nEmbed num: {len(embeds)}"
  if files:
    text += f"\nFile num: {len(files)}"
  return text

def get_full_message(row, bot, guild):
  mid, ctime, author, channel, content, embeds, files = get_message_from_row(row, bot, guild)
  text = (f"Time: {ctime} UTC\n"
          f"Author: {author}\n"
          f"Channel: {channel}")
  if content:
    text += "\n\n" + content
  embed_post = None
  for embed in embeds:
    try:
      embed_post = discord.Embed.from_dict(embed)
      if len(embed_post) > 0:
        break
    except:
      pass
  files_post = []
  for file_name in files:
    if os.path.isfile(f"{path}/{file_name}"):
      files_post.append(discord.File(f"{path}/{file_name}", filename=file_name.split("_", 1)[-1]))
  return text, embed_post, files_post
  
def clean_message_files(row):
  if isinstance(row, dict):
    files = row["files"]
  else:
    files = row[-1]
  files = json_load_list(files)
  for file_name in files:
    try:
      os.remove(f"{path}/{file_name}")
    except:
      pass
      
async def send_temp_message(messageable, content, timeout=10.0):
  # send a temporary message which will disappear after timeout
  msg = await messageable.send(f"{content}\nThis message will disappear in {round(timeout)}s.")
  start_time = time.perf_counter()
  while True:
    await asyncio.sleep(1)
    lefttime = timeout - (time.perf_counter() - start_time)
    if lefttime < 0:
      break
    await msg.edit(content=f"{content}\nThis message will disappear in {round(lefttime)}s.")
  await msg.delete()
  
async def wait_user_confirmation(context, content, timeout=30.0):
  # Send a message to ask for a user confirmation, return True if the user replies yes, False if timeout or user replies no
  msg = await context.send(f"{content} (Yes/No)")
  def confirm(m):
    return (m.author.id == context.author.id and
      m.channel == context.message.channel and
      m.content.lower() in ["yes", "no"])
  try:
    reply = await context.bot.wait_for("message", timeout=timeout, check=confirm)
  except asyncio.TimeoutError:
    return False, msg
  if reply.content.lower() in ["yes"]:
    return True, msg
  else:
    return False, msg
    
async def request_response(context, content, timeout=30.0, *, converter=lambda x:x, loop=False, invalid_response=""):
  # ask for a user response
  if (not inspect.isfunction(converter) and not isinstance(converter, commands.Converter) and 
    not (inspect.isclass(converter) and issubclass(converter, commands.Converter))):
    raise TypeError("Converter must be a converter class or a function.")
  msg = await context.send(content)
  def confirm(m):
    return (m.author.id == context.author.id and m.channel == context.message.channel)
  if not invalid_response:
    invalid_response = f"Sorry {context.author.mention} but your input is not valid."
  async def convert(arg):
    if inspect.isfunction(converter):
      return converter(arg)
    elif isinstance(converter, commands.Converter):
      return await converter.convert(context, arg)
    else:
      return await converter().convert(context, arg)
  while True:
    try:
      reply = await context.bot.wait_for("message", timeout=timeout, check=confirm)
    except asyncio.TimeoutError:
      return None, msg
    try:
      return (await convert(reply.content), msg)
    except:
      await context.send(invalid_response)
      if not loop:
        return None, msg
    

async def multiple_choice(context, content, timeout=30.0, *, num:int=None, emojis=None):
  # A multiple choice question waiting for a reaction response
  assert (num or emojis), f"must have at least one input: num or emojis"
  if num is None:
    num = len(emojis)
  if emojis is None:
    emojis = num_emojis[1:num+1]
  assert (len(emojis) == num), f"emojis should have the length {num}"
  msg = await context.send(f"{content}")
  for emoji in emojis:
    await msg.add_reaction(emoji)
  def check(reaction, user):
    return user == context.message.author and reaction.message.id == msg.id and reaction.emoji in emojis
  try:
    reaction, user = await context.bot.wait_for("reaction_add", timeout=timeout, check=check)
  except asyncio.TimeoutError:
    await msg.clear_reactions()
    return None, msg
  return emojis.index(reaction.emoji), msg
  
async def save_message(bot, message):
  # ensure the synchronization of this method
  row = await message_to_row(message)
  bot.db[message.channel.guild.id].insert_or_update("messages", *row)
  
  
