import os
import time
import discord
from discord.ext import commands
from base.modules.access_checks import has_admin_role
from base.modules.message_helper import wait_user_confirmation

class SettingsManagementCog(commands.Cog, name="Settings Management Commands"):
  def __init__(self, bot):
    self.bot = bot

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to modify my settings.")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `{context.prefix}{context.command.qualified_name}`.")
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, (LookupError, TypeError,)):
      await context.send(f"Sorry {context.author.mention}, but {error.original}")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while modifying the setting")

  @commands.group(
    name="settings",
    brief="Modifies settings",
    usage="<command>",
    case_insensitive = True,
    invoke_without_command=True,
    aliases=["setting", "conf", "config", "configure"]
  )
  @has_admin_role()
  async def _settings(self, context):
    await context.send_help("settings")

  @_settings.command(
    name="set",
    brief="Modifies a setting",
    help="Parameters:\n key - the name of the setting\n value - the value of the setting)",
    description="This command modifies a setting."
  )
  @has_admin_role()
  async def _set_setting(self, context, key, *, value):
    value = await self.bot.set_setting(context.guild, key, value, context)
    await context.send(f"```{key} has been set to {value}.```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="modified a setting",
      description=f"{key}:\n{value}", timestamp=context.message.created_at
    )

  @_settings.command(
    name="get",
    brief="Gets a setting",
    help="Parameters:\n key - the name of the setting",
    description="This command gets the value of a setting."
  )
  @has_admin_role()
  async def _get_setting(self, context, key):
    value = self.bot.get_setting(context.guild, key)
    await context.send(f"```{key}: {value}```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="fetched a setting",
      description=f"{key}:\n{value}", timestamp=context.message.created_at
    )

  @_settings.command(
    name="add",
    brief="Adds a new setting",
    help="Parameters:\n key - the name of the setting\n value - the value of the setting",
    description="This command adds a new setting."
  )
  @commands.is_owner()
  async def _add_setting(self, context, key, *, value):
    self.bot.add_setting(context.guild, key, value)
    await context.send(f"```{key} has been added to the settings.```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="added a setting",
      description=f"{key}:\n{value}", timestamp=context.message.created_at
    )


  @_settings.command(
    name="describe",
    brief="Adds a description to a setting",
    help="Parameters:\n key - the name of the setting\n value - the value of the description",
    description="This command adds a description to a setting.",
    aliases=["des", "description"]
  )
  @commands.is_owner()
  async def _add_description(self, context, key, *, value):
    self.bot.add_setting_description(context.guild, key, value)
    await context.send(f"```{key} has been described.```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="described a setting",
      description=f"{key}:\n{value}", timestamp=context.message.created_at
    )



  @_settings.command(
    name="rm",
    brief="Removes a setting",
    help="Parameters:\n key - the name of the setting",
    description="This command removes a setting."
  )
  @commands.is_owner()
  async def _remove_setting(self, context, key):
    if key in self.bot.default_settings:
      response, msg = await wait_user_confirmation(context, 
        f"Warning: removing a default setting is not recommended. Are you sure you want to process?")
      if not response:
        await context.send(f"Operaction cancelled.")
        return
    self.bot.rm_setting(context.guild, key)
    await context.send(f"```{key} has been removed from the settings.```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="removed a setting",
      description=f"Setting:\n{key}", timestamp=context.message.created_at
    )

  @_settings.command(
    name="info",
    brief="Shows all settings",
    description="This command shows all settings of the bot.",
  )
  @has_admin_role()
  async def _info_setting(self, context):
    await context.send(f"```{self.bot.settings[context.guild.id].info()}```")
    
  @_settings.command(
    name="reset",
    brief="Reset all default settings",
    description="This command resets all settings of the bot to default.",
  )
  @has_admin_role()
  async def _reset_setting(self, context):
    await self.bot.reset_settings(context)
    await context.send(f"```All settings are reset to default.```")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="reset settings to default values",
      timestamp=context.message.created_at
    )



#This function is needed for the load_extension routine.
def setup(bot):
  bot.add_cog(SettingsManagementCog(bot))
  print("Added settings management.")
