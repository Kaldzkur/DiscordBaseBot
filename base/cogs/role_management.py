import discord
import typing
from discord.ext import commands, tasks
from base.modules.access_checks import has_mod_role
from base.modules.basic_converter import EmojiUnion
from base.modules.constants import CACHE_PATH as path
import os
import json
import logging

logger = logging.getLogger(__name__)

class RoleManagementCog(commands.Cog, name="Role Management Commands"):
  def __init__(self, bot):
    self.bot = bot
    self.role_links = {}
    if not os.path.isdir(path):
      os.mkdir(path)
    try:
      with open(f"{path}/role_links.json") as f:
        data = json.load(f)
        if isinstance(data, dict):
          for key in data:
            if isinstance(data[key], list):
              self.role_links[int(key)] = data[key]
    except:
      pass
    for guild in self.bot.guilds:
      self.init_guild(guild)
      
  def init_guild(self, guild):
    if guild.id not in self.role_links:
      self.role_links[guild.id] = []

  def cog_unload(self):
    try:
      with open(f'{path}/role_links.json', 'w') as f:
        json.dump(self.role_links, f)
    except:
      pass

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
  async def on_raw_reaction_add(self, payload):
    guild = self.bot.get_guild(payload.guild_id)
    user = guild.get_member(payload.user_id)
    user_role_ids = [role.id for role in user.roles]
    message = None
    for role_link in self.role_links[payload.guild_id]:
      if str(payload.emoji) != role_link["emoji"]:
        continue
      if ("channel" in role_link and role_link["channel"] == payload.channel_id and
          "mod_role" in role_link and role_link["mod_role"] in user_role_ids):
          if message is None:
            message = await guild.get_channel(payload.channel_id).fetch_message(payload.message_id)
          author = message.author
          role = guild.get_role(role_link["role"])
          if role not in author.roles:
            await author.add_roles(role, reason=f"Approved by {user}")
            logger.debug(f"Added role {role} to user {author} approved by {user}.")
            fields = {
              "Member": f"{author.mention}\nUID: {author.id}",
              "Added Role": f"{role.mention}\nRID: {role.id}",
            }
            await self.bot.log_message(guild, "MOD_LOG",
              user=user, action="approved the role",
              fields=fields
            )
      elif "message" in role_link and role_link["message"] == payload.message_id:
        role = guild.get_role(role_link["role"])
        if role not in user.roles:
          await user.add_roles(role, reason=f"self authentication")
          logger.debug(f"Added role {role} to user {user} by self authentication.")
          fields = {
            "Added Role": f"{role.mention}\nRID: {role.id}",
          }
          await self.bot.log_message(guild, "MOD_LOG",
            user=user, action="completed self authentication",
            fields=fields
          )


  @commands.group(
    name="rlink",
    brief="Links reactions and roles",
    help="Automatically assigns roles based on the reaction (verification).",
    invoke_without_command=True,
  )
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @has_mod_role()
  async def _rlink(self, context, member: discord.Member = None):
    await context.send_help("rlink")

  @_rlink.command(
    name="mod",
    brief="Assigns a role based on a mod's reaction",
    help="Automatically assigns roles based on the reaction (verification) from mods. The role will be assigned if someone with a mod role adds a reaction to the member's message in the specific channel.",
    usage="<#channel> <@mod_role>... <emoji> <@assigned_role>",
  )
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @has_mod_role()
  async def _rlink_mod(self, context, channel: discord.TextChannel, mod_role: discord.Role, emoji: EmojiUnion, role: discord.Role):
    # check the permissions
    if context.author.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, you do not have enough permission to manage {role.mention}")
      return
    if context.guild.me.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, I do not have enough permission to manage {role.mention}")
      return
    if mod_role < role:
      await context.send(f"Sorry {context.author.mention}, {mod_role.mention} do not have enough permission to manage {role.mention}")
      return
    self.role_links[context.guild.id].append({
      "role": role.id,
      "channel": channel.id,
      "mod_role": mod_role.id,
      "emoji": emoji,
    })
    await context.send(f"Role-reaction link added.")
    fields = {
      "Role": f"{role.mention}\nRID: {role.id}",
      "Channel":f"{channel.mention}\nCID: {channel.id}",
      "Mod Role":f"{mod_role.mention}\nCID: {mod_role.id}",
      "Emoji":f"{emoji}"
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="added a role-reaction link",
      fields=fields, timestamp=context.message.created_at
    )

  @_rlink.command(
    name="self",
    brief="Assigns a role based on a user's reaction",
    help="Automatically assigns roles based on the reaction (verification) from members. The role will be assigned if a member adds a reaction to the target message.",
    usage="<messageID> <emoji> <@assigned_role>",
  )
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @has_mod_role()
  async def _rlink_self(self, context, message: discord.Message, emoji: EmojiUnion, role: discord.Role):
    # check the permissions
    if context.author.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, you do not have enough permission to manage {role.mention}")
      return
    if context.guild.me.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, I do not have enough permission to manage {role.mention}")
      return
    self.role_links[context.guild.id].append({
      "role": role.id,
      "channel": message.channel.id,
      "message": message.id,
      "emoji": emoji,
    })
    await context.send(f"Role-reaction link added.")
    fields = {
      "Role": f"{role.mention}\nRID: {role.id}",
      "Message ID":f"{message.id}",
      "Emoji":f"{emoji}"
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="added a role-reaction link",
      fields=fields, timestamp=context.message.created_at
    )
  
  @_rlink.command(
    name="remove",
    brief="Removes role-reaction links",
    help="Removes all role-reaction links for the assigned role.",
    aliases=["rm"]
  )
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @has_mod_role()
  async def _rlink_rm(self, context, role: discord.Role):
    # check the permissions
    if context.author.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, you do not have enough permission to manage {role.mention}")
      return
    if context.guild.me.top_role <= role:
      await context.send(f"Sorry {context.author.mention}, I do not have enough permission to manage {role.mention}")
      return
    # remove all links to the role
    self.role_links[context.guild.id] = [role_link for role_link in self.role_links[context.guild.id] if role_link["role"] != role.id]
    await context.send(f"Role-reaction link removed.")
    fields = {
      "Role": f"{role.mention}\nRID: {role.id}",
    }
    await self.bot.log_message(context.guild, "MOD_LOG",
      user=context.author, action="removed role-reaction links",
      fields=fields, timestamp=context.message.created_at
    )  
    
  @_rlink.command(
    name="list",
    brief="Shows a list of role-reaction links",
    help="Shows a list of role-reaction links.",
  )
  @commands.has_permissions(manage_roles=True)
  @commands.bot_has_permissions(manage_roles=True)
  @has_mod_role()
  async def _rlink_list(self, context):
    if len(self.role_links[context.guild.id]) == 0:
      await context.send("Sorry, but no role-reaction link is found in this server.")
      return
    embed = discord.Embed(title=f"Role-Reaction Links", colour=discord.Colour.green(), timestamp=context.message.created_at)
    i = 1
    for role_link in self.role_links[context.guild.id]:
      role = context.guild.get_role(role_link["role"])
      emoji = role_link["emoji"]
      channel = context.guild.get_channel(role_link['channel'])
      if not role or not channel:
        continue
      if "mod_role" in role_link:
        mod_role = context.guild.get_role(role_link["mod_role"])
        msg = (
          f"Type: Assign role to author when a mod role react\n"
          f"Role Assigned: {role.mention}\n"
          f"Auth Reaction: {emoji}\n"
          f"Auth Channel: {channel.mention}\n"
        )
      elif "message" in role_link:
        message = await channel.fetch_message(role_link["message"])
        msg = (
          f"Type: Assign role to member when reacting to the target message\n"
          f"Role Assigned: {role.mention}\n"
          f"Auth Reaction: {emoji}\n"
          f"Auth Message: {message.jump_url}\n"
        )
      else:
        continue
      embed.add_field(name=f"Link {i}:", value=msg, inline=False)
      i += 1
    embed.set_footer(text="R-R LINK")
    await context.send(content=None, embed=embed)
      


def setup(bot):
  bot.add_cog(RoleManagementCog(bot))
  logger.info("Added role management.")
