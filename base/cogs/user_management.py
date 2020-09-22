import time
from datetime import datetime
import discord
import re
import typing
from pathlib import Path
from discord.ext import commands, tasks
from base.modules.access_checks import has_mod_role, has_admin_role, is_server_owner
from base.modules.message_helper import wait_user_confirmation
from base.modules.basic_converter import MemberOrUser

class UserManagementCog(commands.Cog, name="User Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    self.update_slapcount.start()
    
  def cog_unload(self):
    self.update_slapcount.cancel()
  
  @tasks.loop(hours=1)
  async def update_slapcount(self):
    try:
      await self.bot.set_random_status()
    except Exception as error:
      for guild in self.bot.guilds:
        await self.bot.on_task_error("Set random activity", error, guild)
    now = time.time()
    for guild in self.bot.guilds:
      if self.bot.get_setting(guild, "AUTO_UPDATE") != "ON":
        continue
      try:
        db = self.bot.db[guild.id]
        slaps = db.select("user_warnings")
        if slaps:
          for slap in slaps:
            if slap["count"] > 0 and now > slap["expires"]:
              db.insert_or_update("user_warnings", slap["userid"], slap["username"], 0, slap["expires"])
              title = "Warning(s) expired"
              fields = {"User":f"{slap['username']}\n{slap['userid']}",
                        "Expiry":f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(slap['expires']))} UTC"}
              await self.bot.log_mod(guild, title=title, fields=fields)
          await self.bot.log_mod(guild, title="Updated warning counts")
      except Exception as error:
        await self.bot.on_task_error("Update user warnings", error, guild)
      try:
        mutes = db.select("users_muted")
        mute_role = self.bot.get_mute_role(guild)
        if mutes:
          for muted_user in mutes:
            if now > muted_user["expires"]:
              member = guild.get_member(muted_user["userid"])
              if not member:
                member = None
              else:
                await member.remove_roles(mute_role)
              db.delete_row("users_muted", muted_user["userid"])
              title = "Mute expired"
              fields = {"User":f"{member}\n{muted_user['userid']}",
                        "Expiry":f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(muted_user['expires']))} UTC"}
              await self.bot.log_mod(guild, title=title, fields=fields)
          await self.bot.log_mod(guild, title="Updated muted users")
      except Exception as error:
        await self.bot.on_task_error("Update muted users", error, guild)
      if self.update_slapcount.current_loop > 0:
        # update user stats only after reboot
        try:
          self.bot.update_user_stats(guild)
          await self.bot.log_mod(guild, title="Updated user statistics")
        except Exception as error:
          await self.bot.on_task_error("Update user statistics", error, guild)

  @update_slapcount.before_loop
  async def before_update_slapcount(self):
    await self.bot.wait_until_ready()

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.MissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    elif isinstance(error, commands.BotMissingPermissions):
      await context.send(f"Sorry {context.author.mention}, but I do not have permission to execute that command!")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `?{context.command.qualified_name}`.")
    elif isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command!")
    elif isinstance(error, commands.MaxConcurrencyReached):
      await context.send(f"Sorry {context.author.mention}, but only {error.number} user(s) can execute `?{context.command.qualified_name}` at the same time!")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while executing that command.")
      
  def get_max_warnings(self, guild):
    return self.bot.get_setting(guild, "MAX_WARNINGS")
    
  def get_warn_duration(self, guild):
    return self.bot.get_setting(guild, "WARN_DURATION")

  def get_mute_duration(self, guild):
    return self.bot.get_setting(guild, "MUTE_DURATION")

  @commands.Cog.listener()
  async def on_member_update(self, before, after):
    if before.id == self.bot.user.id:
      return
    if before.nick != after.nick:
      title = f"{before.display_name} changed nickname"
      fields = {
        "Old nickname":before.nick,
        "New nickname":after.nick
      }
      await self.bot.log_audit(before.guild, title=title, description=f"{before}\nID: {before.id}", fields=fields)

  @commands.Cog.listener()
  async def on_user_update(self, before, after):
    if before.id == self.bot.user.id:
      return
    fields = {}
    change = False
    if before.name != after.name:
      fields.update({
        "Old username":before.name,
        "New username":after.name
      })
      change = True
    if before.discriminator != after.discriminator:
      fields.update({
        "Old discriminator":before.discriminator,
        "New discriminator":after.discriminator
      })
      change = True
    if change:
      for guild in self.bot.guilds:       
        await self.bot.log_audit(
          guild,
          title=f"{before.display_name} changed profile",
          description=f"{before}\n{after}\nID: {before.id}",
          fields=fields
        )

  @commands.Cog.listener()
  async def on_member_remove(self, member):
    if member.id == self.bot.user.id:
      return
    channel = member.guild.system_channel
    #If this channel does not exist, get some backup channels.
    if channel is None:
      channel = discord.utils.get(member.guild.text_channels, name="welcome")
    if channel is None:
      channel = discord.utils.get(member.guild.text_channels, name="general")
    if channel is None:
      channel = discord.utils.get(member.guild.text_channels, name="general-chat")
    if channel is not None:
      await channel.send(f"{member} just left the server. :sob:")
    title = f"{member.display_name} just left the server"
    fields = {
      "Account created on":member.created_at,
      "Joined on":member.joined_at
    }
    await self.bot.log_audit(member.guild, title=title, description=f"{member}\nID: {member.id}", fields=fields)
    if False:
      try:
        await member.create_dm()
        embed = discord.Embed(
          title=f"Hey {member}, are you leaving us?",
          description=f"Just in case you want to come back to the {member.guild.name} server, here is a special invite link: {channel.create_invite()}",
          colour=discord.Colour.orange(),
          timestamp=context.message.created_at
        )
        await member.dm_channel.send(content=None, embed=embed)
      except:
        pass

  @commands.Cog.listener()
  async def on_member_join(self, member):
    if member.id == self.bot.user.id:
      return
    title = f"{member.display_name} just joined the server"
    fields = {
      "Account created on":member.created_at,
      "Joined on":member.joined_at
    }
    await self.bot.log_audit(member.guild, title=title, description=f"{member}\nID: {member.id}", fields=fields)
    try:
      await member.create_dm()
      await member.dm_channel.send(
        f"Hi __{member.name}__, welcome to the {member.guild.name} discord server!"
        f"Please read the following sections:\n\n"
        f"__***Rules***__\n"
        f"Be *polite*, *respectful*, and avoid political discussions.  "
        f"You heard us -- *civil* and *friendly*.\n\n"
        f"This discord is a place to kick back, have a mug of Elixir, and chat about the good ol’ days of tossin’ meteors. "
        f"You know, typical stuff.\n\n"
        f"All text should be in English, please. "
        f"If you feel there is a need for a language specific channel, please PM one of the mods and we will arrange one.\n\n"
        f"Questions are always welcome. The developers are around, but let's avoid tagging them too much. "
        f"We don't want to be a pain in the butt.\n\n"
        f"Alternatively feel free to talk about other neat stuff (How neat is that?), "
        f"that you find around the web, worldwide or localwide, we don’t discriminate the regionality of your finds.\n\n"
        f"__Please respect all of Discord's global rules: https://discordapp.com/guidelines__\n\n"
      )
    except: #could not send dm
      pass
    try:
      max_warnings = self.get_max_warnings(member.guild)
      warn_duration = self.get_warn_duration(member.guild)
      await member.dm_channel.send(
        f"__**Warnings**__\n"
        f"When you receive a warning it will expire after {warn_duration} days. If you receive another warning during that time, "
        f"it will expire after {2*warn_duration} days from the time you got the last warning. "
        f"If you get no additional warnings during the expiry time, then all your warnings will be reset."
        f"If you receive more than {max_warnings} warnings without them expiring first, then you will be removed from the server. "
        f"If you want to check the current status of your warnings, use the `?warn info` or `?slap info` command.\n\n"
        f"If you have something to discuss with the mods, then use the `?modmail` command. You can specify the reason for opening the channel using `?modmail your reason`. "
        f"To dispute any warnings, use the `?modmail` command."
      )
    except: #could not send dm
      pass

  #@commands.Cog.listener()
  #async def on_member_ban(self, guild, user):
  #async def on_member_unban(self, guild, user):

  @commands.command(
    name="statistic",
    brief="Displays user activity stats",
    description="Will send a simple overview of tracked user stats on this discord server.",
    help="Note: Moderators are able to see other users' stats with the optional `member` parameter. `member` is usually a @mention, but can also be a users' id.",
    usage="[member]",
    aliases=["statistics"]
  )
  async def _statistic(self, context, member: discord.Member = None):
    if context.author.id not in self.bot.owner_ids and self.bot.get_mod_role(context.guild) not in context.author.roles:
      user = context.author
    else:
      if member is None:
        user = context.author
      else:
        user = member
    total = self.bot.db[context.guild.id].select("user_statistics", user.id)
    if user.id in self.bot.user_stats[context.guild.id]:
      result = self.bot.user_stats[context.guild.id][user.id]
    else:
      result = None
    if not total and not result:
      await context.send("```None```")
    else:
      embed = discord.Embed(
        title=f"{user.name if user.nick is None else user.nick} Statistics",
        description=f"Tracked since August 13 2020",
        colour=discord.Colour.green(),
        timestamp=context.message.created_at
      )
      if total is None:
        msg = result["messages"]
        cmd = result["commands"]
        wrd = result["words"]
        rct = result["reactions"]
        rct_own = result["reacts_to_own"]
      elif result is None:
        msg = total["total_messages"]
        cmd = total["total_commands"]
        wrd = total["total_words"]
        rct = total["total_reacts"]
        rct_own = total["reacts_to_own"]
      else:
        msg = total["total_messages"]+result["messages"]
        cmd = total["total_commands"]+result["commands"]
        wrd = total["total_words"]+result["words"]
        rct = total["total_reacts"]+result["reactions"]
        rct_own = total["reacts_to_own"]+result["reacts_to_own"]
      embed.add_field(name="Messages sent:", value=msg, inline=False)
      if msg > 0:
        embed.add_field(name="Commands sent:", value=f"{cmd} ({round(float(cmd)/msg*100, 2)}%)", inline=False)
      if msg-cmd > 0:
        embed.add_field(name="Word per message(average):", value=f"{round(float(wrd)/(msg-cmd), 2)}", inline=False)
      else:
        embed.add_field(name="Word per message(average):", value=0, inline=False)
      embed.add_field(name="Reactions made:", value=rct, inline=False)
      if rct > 0:
        rct_percent = rct_own/rct *100
      else:
        rct_percent = 0
      embed.add_field(name="Reactions to own messages:", value=f"{rct_own} ({round(rct_percent, 2)}%)", inline=False)
      embed.set_footer(text="USER STATISTICS")
      await context.send(content=None, embed=embed)

  @commands.command(
    name="info",
    brief="Shows user info",
    aliases=["user"],
  )
  @has_mod_role()
  async def _user_info(self, context, members: commands.Greedy[MemberOrUser]):
    if len(members) == 0:
      await context.send(f"Sorry {context.author.mention}, but no valid user(s) were found.")
      return
    for user in members:
      embed = discord.Embed(title=f"User Information", colour=user.colour)
      if user.bot:
        type = "Bot"
      elif user.system:
        type = "User (Discord Official)"
      else:
        type = "User"
      embed.add_field(name=f"{type}:", value=f"{user.name}\n{user}", inline=False)
      embed.add_field(name="ID:", value=f"{user.id}", inline=False)
      embed.add_field(name="Created on:", value=f"{user.created_at}", inline=False)
      embed.set_thumbnail(url=user.avatar_url)
      if hasattr(user, "joined_at"): #member specific attribute
        embed.add_field(name=f"Joined {context.guild.name} on:", value=f"{user.joined_at}", inline=False)
      await context.send(content=None, embed=embed)
    users = "\n".join([f"{user} ({user.id})" for user in members])
    title = "User fetched user information"
    fields = {"User":f"{context.author.mention}\n{context.author}",
              "Target User(s)":users}
    await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)

  @commands.command(
    name="mute",
    brief="Mutes one or more users",
    description="Will apply the `Muted` role to one or more members.",
    help="Note: For this command to work all text channels should have appropriate permissions for the `Muted` role. Unfortunately they have to be assigned to each channel manually. The optional `reason` parameter lets you specify why the user was muted. The duration for all mutes can be set in the bots' settings.",
    usage="members... [reason]",
    aliases=["silence"]
  )
  @has_mod_role()
  async def _mute(self, context, members: commands.Greedy[discord.Member], *, reason="not specified"):
    if len(members) == 0:
      await context.send_help("mute")
      return
    mute_role = self.bot.get_mute_role(context.guild)
    mute_duration = self.get_mute_duration(context.guild) * 86400
    expiry = time.time() + mute_duration
    expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(expiry))
    self.bot.create_tables(context.guild)
    for member in members:
      if member.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I am not capable of muting myself. I like to talk too much.")
        continue
      elif member.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but my owner made himself immune against muting!")
        continue
      self.bot.db[context.guild.id].insert_or_update("users_muted", member.id, expiry)
      await member.add_roles(mute_role)
      await context.send(f"{member.mention} muted.")
      title = f"{member.display_name} has been muted"
      fields = {"User":f"{member}\nID: {member.id}",
                "Reason":reason,
                "Expires":f"{expire_time} UTC"}
      await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
      try:
        dm = [
          f"You have temporarily been ***muted*** in the __{context.guild.name}__ discord. ",
          "To avoid this, please follow the rules of the server.",
          f"```Reason for muting: {reason}\nExpires: {expire_time} UTC```"
        ]
        await member.create_dm()
        await member.dm_channel.send("".join(dm))
      except:
        pass #DM could not be sent

  @commands.command(
    name="unmute",
    brief="Unmutes one or more users",
    description="Will remove the `Muted` role to one or more members.",
    usage="members...",
  )
  @has_mod_role()
  async def _unmute(self, context, members: commands.Greedy[discord.Member]):
    if len(members) == 0:
      await context.send_help("unmute")
      return
    mute_role = self.bot.get_mute_role(context.guild)
    mute_duration = self.get_mute_duration(context.guild) * 86400
    expiry = time.time() + mute_duration
    expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(expiry))
    self.bot.create_tables(context.guild)
    for member in members:
      if member.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I am not capable of unmuting myself. I like to talk too much.")
        continue
      elif member.id == context.author.id:
        await context.send(f"Sorry {context.author.mention}, but you are not capable of unmuting yourself.")
        continue
      elif member.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but my owner made himself immune against muting!")
        continue
      self.bot.db[context.guild.id].delete_row("users_muted", member.id)
      await member.remove_roles(mute_role)
      await context.send(f"{member.mention} unmuted.")
      title = f"{member.display_name} has been unmuted"
      fields = {"User":f"{member}\nID: {member.id}"}
      await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)

  @commands.command(
    name="prune",
    brief="Removes all inactive users from the discord server",
    description="Will remove all inactive members from the discord server.",
    help="Attention: Use with care, as this command will potentially remove lots of users from the discord server.\n\nA confirmation popup will ask you to confirm the choice. The optional `days` parameter lets you specify how many days of not logging in the guild count as inactive. Allowed values are 1 - 30, by default 30 days are used.",
    usage="[days=30]"
  )
  @commands.has_permissions(kick_members=True)
  @commands.bot_has_permissions(kick_members=True)
  @commands.max_concurrency(1)
  @is_server_owner()
  async def _prune(self, context, *, days:int=30):
    if not(1 <= days <= 30):
      await context.send(f"Days must be between 1 and 30 ({days}).")
      return
    result = await context.guild.estimate_pruned_members(days=days)
    response, msg = await wait_user_confirmation(context, f"This operation would remove {result} members from the server. Do you still want to proceed?")
    if response:
      #Disable remove listener while pruning
      self.bot.remove_listener(self.on_member_remove, "on_member_remove")
      await context.guild.prune_members(days=days, compute_prune_count=False)
      self.bot.add_listener(self.on_member_remove, "on_member_remove")
      await context.send(f"Removed {result} members from the server.")
      title = "Users were pruned"
      fields = {"Inactive days":days,
                "Removed members":result}
      await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
    else:
      await context.send(f"Prune operation cancelled.")

  @commands.group(
    name="warn",
    brief="Warns one or more users",
    description="Will warn one or more users. ",
    help="The optional `reason` parameter lets the user know why he has been warned. Warnings expire if no other warnings have been received during the warning exipry set in the bots' settings. After a certain amount of received warnings, the user will be removed from the server.",
    usage="members... [reason]",
    invoke_without_command=True,
    aliases=["slap"]
  )
  @commands.has_permissions(kick_members=True)
  @commands.bot_has_permissions(kick_members=True)
  @has_mod_role()
  async def _warn(self, context, members: commands.Greedy[discord.Member], *, reason="not specified"):
    if len(members) == 0:
      await context.send_help("warn")
      return
    warn_duration = self.get_warn_duration(context.guild) * 86400
    expiry = time.time()
    #If the user_warnings table is missing create a new one
    self.bot.create_tables(context.guild)
    max_warnings = self.get_max_warnings(context.guild)
    for member in members:
      if member.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I am not capable of warning myself. I wouldn't even read it!")
        continue
      elif member.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but my owner made himself immune against warnings! What a jerk!")
        continue
      warn_count = self.bot.db[context.guild.id].select("user_warnings", member.id)
      if warn_count is None:
        warn_count = 0
      else:
        warn_count = warn_count["count"]
      expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(expiry + warn_duration*(warn_count+1)))
      if warn_count+1 <= max_warnings:
        try:
          dm = [
            f"You have received a ***WARNING*** in the __{context.guild.name}__ discord. ",
            "To avoid this, please follow the rules of the server.",
            f"```Reason for warning: {reason}\nNumber of warnings: {warn_count+1}\nExpires: {expire_time} UTC```"
          ]
          if warn_count+1 == max_warnings:
            dm.append(f"Note: You will be removed from the {context.guild.name} server, if you receive another warning before the previous warnings expire.")
          await member.create_dm()
          await member.dm_channel.send("".join(dm))
        except:
          pass #DM could not be sent
        await context.send(f"{self.bot.user.name} \*slaps* {member.mention}.\nSlapcount: {warn_count+1}")
        title = f"{member.display_name} has been warned"
        fields = {"User":f"{member}\nID: {member.id}",
                  "Reason":reason,
                  "Number of warnings":warn_count+1,
                  "Expires":f"{expire_time} UTC"}
        await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
      else:
        try:
          await member.create_dm()
          await member.dm_channel.send(
            f"You have received a ***WARNING*** in the __{context.guild.name}__ discord. "
            f"In addition, you have exceeded the number of allowed warnings. Therefore you have been removed from the server."
            f"```Reason for warning: {reason}\nNumber of warnings: {warn_count+1}```"
          )
        except:
          #DM could not be sent
          pass
        await member.kick(reason="Exceeded number of allowed warnings.")
        await context.send(f"```{member} was forced to leave the server.\nReason: excessive slapcount```")
        title = f"{member.display_name} has been kicked (reached max warnings)"
        fields = {"User":f"{member}\nID: {member.id}",
                  "Reason":reason,
                  "Number of warnings":warn_count+1,
                  "Expires":f"{expire_time} UTC"}
        await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
      self.bot.db[context.guild.id].insert_or_update("user_warnings", member.id, f"{member}", warn_count+1, expiry + warn_duration*(warn_count+1))

  @_warn.command(
    name="info",
    brief="Shows current status of warnings",
    description="Will show the current status of the users' warnings.",
    help="Note for moderators: The optional `members` parameter lets you see other users' warnings.",
    usage="members..."
  )
  async def _warn_info(self, context, members: commands.Greedy[discord.Member]):
    #if not mod:
    if context.author.id not in self.bot.owner_ids and self.bot.get_mod_role(context.guild) not in context.author.roles:
      warning = self.bot.db[context.guild.id].select("user_warnings", context.author.id)
      embed = discord.Embed(title=f"Warning Status", colour=discord.Colour.gold(), timestamp=context.message.created_at)
      embed.add_field(name="User:", value=f"{context.author.mention}", inline=False)
      if warning is None:
        embed.add_field(name="Slapcount:", value="0 slap(s)", inline=False)
      else:
        embed.add_field(name="Slapcount:", value=f"{warning['count']} slap(s)", inline=False)
        embed.add_field(name="Expires:", value=f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(warning['expires']))} UTC", inline=False)
      embed.set_footer(text="SLAP STATUS")
      await context.send(content=None, embed=embed) 
    else:
      if len(members) == 0:
        members = [context.author]
      for member in members:
        warning = self.bot.db[context.guild.id].select("user_warnings", member.id)
        embed = discord.Embed(title=f"Warning Status", colour=discord.Colour.gold(), timestamp=context.message.created_at)
        embed.add_field(name="User:", value=f"{member.mention}", inline=False)
        if warning is None:
          embed.add_field(name="Slapcount:", value="0 slap(s)", inline=False)
        else:
          embed.add_field(name="Slapcount:", value=f"{warning['count']} slap(s)", inline=False)
          embed.add_field(name="Expires:", value=f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(warning['expires']))} UTC", inline=False)
        embed.set_footer(text="SLAP STATUS")
        await context.send(content=None, embed=embed)

  @_warn.command(
    name="remove",
    brief="Removes one or more warnings",
    description="Will remove one or more warnings from a user.",
    help="By default one warning is removed from all members specified in the `member` parameter. The optional `number` parameter lets you specify how many warnings will be removed.",
    usage="members... [number=1]",
    aliases=["rm"]
  )
  @commands.has_permissions(kick_members=True)
  @commands.bot_has_permissions(kick_members=True)
  @has_mod_role()
  async def _warn_rm(self, context, members: commands.Greedy[discord.Member], number=1):
    if len(members) == 0:
      await context.send_help("warn remove")
      return
    max_warnings = self.get_max_warnings(context.guild)
    warn_duration = self.get_warn_duration(context.guild) * 86400
    for member in members:
      if member.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I cannot have warnings so why would you remove them?")
        continue
      elif member.id == context.author.id:
        await context.send(f"Sorry {context.author.mention}, but you can't remove your own warnings!")
        continue
      elif member.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but my owner is immune to warnings.")
        continue
      warn_count = self.bot.db[context.guild.id].select("user_warnings", member.id)
      if warn_count is None:
        warn_count = 0
      else:
        expiry = warn_count["expires"]
        warn_count = warn_count["count"]
      if warn_count > 0:
        number = min(warn_count, number)
        new_warn_count = warn_count-number
        new_expiry = expiry - warn_duration*number
        expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(new_expiry))
        self.bot.db[context.guild.id].insert_or_update("user_warnings", member.id, f"{member}", new_warn_count, new_expiry)
        try:
          await member.create_dm()
          await member.dm_channel.send(
            f"{context.author} has removed {number} warning(s).\n```Remaining warnings: {new_warn_count}\nExpires: {expire_time} UTC```"
          )
        except:
          #DM could not be sent
          pass
        await context.send(
          f"{self.bot.user.name} removed {number} slap(s) from  {member.mention}.\nSlapcount: {new_warn_count}"
        )
        title = f"{context.author.display_name} removed warnings"
        fields = {"User":f"{context.author.mention}\n{context.author}",
                  "Removed warnings":number,
                  "From":f"{member}\nID: {member.id}",
                  "Expires":f"{expire_time} UTC"}
        await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
      else:
        await context.send(f"{member} has no warnings")

  @commands.command(
    name="kick",
    brief="Kicks one or more users",
    description="Will kick all members specified in the `members` parameter from the discord server.",
    help="Note for moderators: The optional reason parameter lets you specify why the user has been removed from the discord server.",
    usage="members... [reason='not specified']"
  )
  @commands.has_permissions(kick_members=True)
  @commands.bot_has_permissions(kick_members=True)
  @has_mod_role()
  async def _kick(self, context, members: commands.Greedy[discord.Member], *, reason="not specified"):
    if len(members) == 0:
      await context.send_help("kick")
      return
    for member in members:
      if member.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I can't kick myself. If you want to kick me, do it yourself!")
        continue
      elif member.id == context.author.id:
        await context.send(f"Sorry {context.author.mention}, but you can't kick yourself. If you want to leave, just leave!")
        continue
      elif member.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but I can't betray my owner!")
        continue
      await member.kick(reason=reason)
      await context.send(f"```{member} has been kicked from the server.```")
      title = f"{member.display_name} was kicked from server"
      fields = {"User":f"{member}\nID: {member.id}",
                "Reason":reason}
      await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)

  @commands.group(
    name="ban",
    brief="Bans user(s)",
    description="Will ban all users specified in the `users` parameter.",
    help="The `users` can be either mentions (using @), names (with 4-digit number), or user ids. If the user is currently not in the server, then you have to use the user id.\nThe `days` parameter is optional and can be between 1 and 7. For example, 7 means all of the users' messages of the past 7 days will be deleted.",
    invoke_without_command=True
  )
  @commands.has_permissions(ban_members=True)
  @commands.bot_has_permissions(ban_members=True)
  @has_mod_role()
  async def _ban(self, context, users: commands.Greedy[MemberOrUser], days: typing.Optional[int] = 1, *, reason="not specified"):
    if len(users) == 0:
      await context.send(f"Sorry {context.author.mention}, but I could not find the specified user(s).")
      return
    if not(0 <= days <= 7):
      await context.send(f"Sorry {context.author.mention}, `days` needs to be between 0 and 7. Refer to `?help ban` for more information.")
      return
    for user in users:
      if user.id == self.bot.user.id:
        await context.send(f"Sorry {context.author.mention}, but I can't ban myself. If you want to ban me, do it yourself!")
        continue
      elif user.id == context.author.id:
        await context.send(f"Sorry {context.author.mention}, but you can't ban yourself. If you want to leave, just leave!")
        continue
      elif user.id in self.bot.owner_ids:
        await context.send(f"Sorry {context.author.mention}, but I can't betray my owner!")
        continue
      await context.guild.ban(user, reason=reason, delete_message_days=days)
      await context.send(f"```{user} has been banned from the server.```")
      title = f"{user.display_name} was banned from server"
      fields = {"User":f"{user}\nID: {user.id}",
                "Reason":reason}
      await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)

  @_ban.command(
    name="info",
    brief="Shows all banned users",
    description="Will show a list of all banned users.",
  )
  @commands.has_permissions(ban_members=True)
  @commands.bot_has_permissions(ban_members=True)
  @has_mod_role()
  async def _ban_info(self, context):
    bans = await context.guild.bans()
    for i, ban in enumerate(bans):
      await context.send(f"Banned User {i}: ```User: {ban.user.name}({ban.user})\nUser ID: {ban.user.id}\nReason:{ban.reason}```")

  @_ban.command(
    name="rm",
    brief="Unbans a user",
    help="A command to unban (only) one user from the server. The user should be either the full username or the user id.",
    usage="user [reason]",
    aliases=["remove"]
  )
  @commands.has_permissions(ban_members=True)
  @commands.bot_has_permissions(ban_members=True)
  @has_mod_role()
  async def _unban(self, context, member=None, *, reason="not specified"):
    if member is None:
      await context.send_help("ban rm")
      return
    banned_users = await context.guild.bans()
    if "#" in member:
      member_name, member_discriminator = member.split('#')
      for ban in banned_users:
        if (ban.user.name, ban.user.discriminator) == (member_name, member_discriminator):
          await context.guild.unban(ban.user)
          await context.send(f"{ban.user} has been unbanned from the server.")
          title = f"{ban.user.display_name} was unbanned from server"
          fields = {"User":f"{ban.user.name}\n{ban.user}",
                    "Reason":reason}
          await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
          break
    else:
      #The passed member is an id.
      if "@" in member:
        #<@!123456789>
        user_id = int(member[3:-1])
      else:
        user_id = int(member)
      for ban in banned_users:
        if ban.user.id == user_id:
          await context.guild.unban(ban.user)
          await context.send(f"```{ban.user} has been unbanned from the server.```")
          title = f"{ban.user.display_name} was unbanned from server"
          fields = {"User":f"{ban.user}\nID: {ban.user.id}",
                    "Reason":reason}
          await self.bot.log_mod(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
          break

def setup(bot):
  bot.add_cog(UserManagementCog(bot))
  print("Added user management.")
