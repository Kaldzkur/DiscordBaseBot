import discord
import os
import typing
import json
from pathlib import Path
from discord.ext import commands
from base.modules.constants import CACHE_PATH as path
from base.modules.serializable_object import SecretChannelEntry, dump_json
from base.modules.async_timer import run_bot_coroutine
import logging

logger = logging.getLogger(__name__)

class SecretChannelCog(commands.Cog, name="General Commands"):
  def __init__(self, bot):
    self.bot = bot
    self.initialized = {} # whether the bot has scanned the modmail channels
    if not os.path.isdir(path):
      os.mkdir(path)
    self.secret_channels = SecretChannelEntry.from_json(f'{path}/secret_channels.json')
    for guild in self.bot.guilds:
      self.init_guild(guild)
    
  def init_guild(self, guild):
    if guild.id not in self.secret_channels:
      self.secret_channels[guild.id] = []
    if guild.id not in self.initialized:
      self.initialized[guild.id] = False
    run_bot_coroutine(self.bot, guild, self.start_auto_delete, guild)
    
  def cog_unload(self):
    for guild in self.bot.guilds:
      self.stop_auto_delete(guild)
    dump_json(self.secret_channels, f'{path}/secret_channels.json')

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.MissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    elif isinstance(error, commands.BotMissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but I do not have permission to execute that command!")
    elif isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `{context.command.qualified_name}`.")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while executing that command.")
      
  def get_secret_channel(self, channel):
    for ch in self.secret_channels[channel.guild.id]:
      if ch["channel"] == channel.id:
        return ch
    return None
      
  async def start_auto_delete(self, guild, forceStart=False):
    if not self.initialized[guild.id]:
      if self.get_auto_modmail(guild) or forceStart:
        filtered_secret_channels = []
        for channel_entry in self.secret_channels[guild.id]:
          if await channel_entry.set_auto_delete(guild, self) is not None: # the channel is not found
            filtered_secret_channels.append(channel_entry)
        self.secret_channels[guild.id] = filtered_secret_channels
        self.initialized[guild.id] = True
    
  def stop_auto_delete(self, guild):
    if self.initialized[guild.id]:
      self.initialized[guild.id] = False
      for channel_entry in self.secret_channels[guild.id]:
        channel_entry.cancel()
        
  async def change_auto_delete(self, state, guild):
    if state == "ON":
      await self.start_auto_delete(guild, True)
    else:
      self.stop_auto_delete(guild)
      
  def get_expiry(self, guild):
    return self.bot.get_setting(guild, "MODMAIL_EXPIRY")
  
  def get_auto_modmail(self, guild):
    auto_modmail = self.bot.get_setting(guild, "AUTO_MODMAIL")
    if auto_modmail == "ON":
      return True
    else:
      return False

          
  @commands.group(
    name="modmail",
    brief="Private channel with mods",
    help="This command opens a private text channel with the mods. Moderators and admins can use the option @member to open a modmail for a member.",
    usage="[@member] [reason]",
    case_insensitive = True,
    invoke_without_command=True
  )
  @commands.bot_has_permissions(manage_channels=True)
  async def _modmail(self, context, member:typing.Optional[discord.Member], *, reason=""):
    mod_role = self.bot.get_mod_role(context.guild)
    admin_role = self.bot.get_admin_role(context.guild)
    roles = [x for x in [mod_role, admin_role] if x is not None]
    #if the author is not a mod or admin, or no member is specified, open the channel for the author
    if (mod_role not in context.author.roles and admin_role not in context.author.roles and context.author.id not in self.bot.owner_ids):
      member = None
    await self.create_secret_channel(context, reason, roles, member=member)
    try:
      await context.message.delete()
    except:
      pass

  async def create_secret_channel(self, context, reason, roles, prefix="mail-", member = None):
    #Channel permissions for the bot
    permissions = {
      context.guild.me: discord.PermissionOverwrite(
        create_instant_invite=False, manage_channels=True, manage_roles=True, manage_webhooks=False, read_messages=True,
        send_messages=True, send_tts_messages=True, manage_messages=True, embed_links=True, 
        attach_files=True, read_message_history=True, mention_everyone=True, use_external_emojis=True, add_reactions=True,
        priority_speaker=False, stream=False, connect=False, speak=False, mute_members=False, deafen_members=False,
        move_members=False, use_voice_activation=False, 
      )
    }
    #Restrict access to @everyone
    permissions[context.guild.default_role] = discord.PermissionOverwrite(
      create_instant_invite=False, manage_channels=False, manage_roles=False, manage_webhooks=False, read_messages=False,
      send_messages=False, send_tts_messages=False, manage_messages=False, embed_links=False, 
      attach_files=False, read_message_history=False, mention_everyone=False, use_external_emojis=False, add_reactions=False,
      priority_speaker=False, stream=False, connect=False, speak=False, mute_members=False, deafen_members=False,
      move_members=False, use_voice_activation=False
    )
    #Channel permissions for the bot owners
    for owner_id in self.bot.owner_ids:
      owner = context.guild.get_member(owner_id)
      if owner is not None:
        permissions[owner] = discord.PermissionOverwrite(
          create_instant_invite=False, manage_channels=False, manage_roles=False, manage_webhooks=False, read_messages=True,
          send_messages=True, send_tts_messages=False, manage_messages=False, embed_links=False, 
          attach_files=True, read_message_history=True, mention_everyone=False, use_external_emojis=False, add_reactions=True,
          priority_speaker=False, stream=False, connect=False, speak=False, mute_members=False, deafen_members=False,
          move_members=False, use_voice_activation=False
        )
    for role in roles:
      #Add permissions
      permissions[role] = discord.PermissionOverwrite(
        create_instant_invite=False, manage_channels=False, manage_roles=False, manage_webhooks=False, read_messages=True,
        send_messages=True, send_tts_messages=False, manage_messages=False, embed_links=False, 
        attach_files=True, read_message_history=True, mention_everyone=False, use_external_emojis=False, add_reactions=True,
        priority_speaker=False, stream=False, connect=False, speak=False, mute_members=False, deafen_members=False,
        move_members=False, use_voice_activation=False
      )
    #Get the mod-queue category if it exists
    mod_queue_name = f"{context.guild.me.name}s-queue"
    mod_queue = discord.utils.get(context.guild.categories, name=mod_queue_name)
    if mod_queue is None:
      mod_queue = await context.guild.create_category(
        mod_queue_name,
        overwrites=permissions,
      )
    if member is None:
      user = context.author
    else:
      user = member
    #Add member permission
    permissions[user] = discord.PermissionOverwrite(
      create_instant_invite=False, manage_channels=False, manage_roles=False, manage_webhooks=False, read_messages=True,
      send_messages=True, send_tts_messages=False, manage_messages=False, embed_links=False, 
      attach_files=True, read_message_history=True, mention_everyone=False, use_external_emojis=False, add_reactions=True,
      priority_speaker=False, stream=False, connect=False, speak=False, mute_members=False, deafen_members=False,
      move_members=False, use_voice_activation=False
    )
    mail_channel = await context.guild.create_text_channel(
      f"{prefix}{user.name}",
      topic=reason,
      category=mod_queue,
      position=len(mod_queue.text_channels),
      overwrites=permissions,
      reason=f"{prefix} for {user}"
    )
    secret_channel_entry = SecretChannelEntry(user, mail_channel)
    self.secret_channels[context.guild.id].append(secret_channel_entry)
    mods = " or ".join([f"{role.mention}s" for role in roles])
    msg = [
      f"Hey {user.mention}! Here is your private, temporary modmail channel. ",
      f"It's a good time to give additional information regarding your request. One of the {mods} will get back to you as soon as someone is available. ",
      f"Type `{self.bot.get_guild_prefix(context.guild)}modmail close` to close the channel."
    ]
    if len(reason) > 0:
      msg.append(f"\n```{reason}```")
    await mail_channel.send("".join(msg))
    if self.get_auto_modmail(context.guild):
      await secret_channel_entry.set_auto_delete(context.guild, self)
    fields = {
              "Channel":f"{mail_channel.name}\nCID: {mail_channel.id}",
              "Reason":reason if reason else "No reason specified"
    }
    content = {
      "user":user,
      "action":f"opened a {prefix[0:-1]}",
      "timestamp":context.message.created_at,
      "fields":fields,
    }
    if member:
      content["user"] = context.author
      content["action"] = f"was forced in a {prefix[0:-1]}"
      content["target"] = user
    await self.bot.log_message(context.guild, "MOD_LOG", **content)
  @_modmail.command(
    name="alive",
    brief="Modmail won't auto expire",
    help="This command keeps a modmail channel alive until it is explicitly closed.",
  )
  @commands.bot_has_permissions(manage_channels=True)
  async def _keep_alive(self, context):
    secret_channel = self.get_secret_channel(context.channel)
    if secret_channel is None:
      await context.send("This channel cannot be affected this command.")
      return
    command_author = context.message.author
    mod_role = self.bot.get_mod_role(context.guild)
    admin_role = self.bot.get_admin_role(context.guild)
    roles = [x for x in [mod_role, admin_role] if x is not None]
    # check permissions
    if (mod_role in command_author.roles or admin_role in command_author.roles or
      command_author.id in self.bot.owner_ids or command_author.id == secret_channel["user"]):
      if (not secret_channel["alive"] and secret_channel.cancel()):
        secret_channel["alive"] = True
        await context.send("Channel expiry removed.")
        await self.bot.log_message(context.guild, "MOD_LOG",
          user=context.author,
          action="removed channel expiry",
          timestamp=context.message.created_at,
          fields={"Channel":f"{context.channel.name}\nCID: {context.channel.id}",},
        )
      else:
        await context.send("This channel has no expiry.")
    else:
      raise commands.MissingPermissions()

  @_modmail.command(
    name="close",
    brief="Closes a modmail channel",
    help="This command closes a private text channel with the mods. This only works if it is used from within a modmail channel.",
  )
  @commands.bot_has_permissions(manage_channels=True)
  async def _modmail_close(self, context):
    secret_channel = self.get_secret_channel(context.channel)
    if secret_channel is None:
      await context.send("This channel cannot be closed with this command.")
      return
    command_author = context.message.author
    mod_role = self.bot.get_mod_role(context.guild)
    admin_role = self.bot.get_admin_role(context.guild)
    roles = [x for x in [mod_role, admin_role] if x is not None]
    # check permissions
    if (mod_role in command_author.roles or admin_role in command_author.roles or
      command_author.id in self.bot.owner_ids or command_author.id == secret_channel["user"]):
      secret_channel.cancel()
      await self.delete_secret_channel(context.message.channel, self.bot.get_user(secret_channel["user"]), f"Deleted by {command_author.mention}")
    else:
      raise commands.MissingPermissions()


  async def delete_secret_channel(self, channel, user, reason="No reason", ch_type="mail"):
    mailstore = Path(f"./{ch_type}")
    if not mailstore.is_dir():
      mailstore.mkdir(parents=True, exist_ok=True)
    logfile = Path(f"./{ch_type}/{channel.name[len(ch_type)+1:]}_{channel.id}.txt")
    msg_count = 0
    with logfile.open(mode="w") as conversation:
      conversation.write(f"Message Log of {ch_type} in {channel.guild.name}:\n\n")
      async for message in channel.history(limit=None, oldest_first=True):
        conversation.write(f"{message.author.name}:\n  {message.content}\n---------------\n")
        msg_count += 1
    try:
      await user.create_dm()
      await user.dm_channel.send(
        f"Hey {user.mention}, the {ch_type} in the {channel.guild.name} Discord is closed now. Here is your conversation as a .txt file [{msg_count} message(s)]:",
        file=discord.File(logfile)
      )
      #os.remove(logfile)
    except discord.Forbidden:
      pass #DM could not be sent
    await channel.delete(reason=f"{ch_type} was closed")
    secret_channel = self.get_secret_channel(channel)
    if secret_channel is not None:
      self.secret_channels[channel.guild.id].remove(secret_channel)
    await self.bot.log_message(channel.guild, "MOD_LOG",
      user=user,
      action=f"deleted a {ch_type}",
      fields={"Reason":reason},
    )
        
        
def setup(bot):
  bot.add_cog(SecretChannelCog(bot))
  logger.info("Added secret channel management.")
