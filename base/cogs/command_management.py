import discord
from discord.ext import commands
from base.modules.access_checks import has_admin_role, can_edit_commands
from base.modules.custom_commands import json_load_dict, get_cmd_attributes, set_new_cmd
from base.modules.basic_converter import cmd_name_converter, cmd_add_converter
import json

class CommandCog(commands.Cog, name="Command Management"):
  def __init__(self, bot):
    self.bot = bot

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to execute that command.")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `?{context.command.qualified_name}`:\n{error}")
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, commands.CommandRegistrationError):
      await context.send(f"Sorry {context.author.mention}, but your operation failed:\n{error.original}")
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, (NameError, LookupError)):
      await context.send(f"Sorry {context.author.mention}, but there is a lookup error:\n{error.original}")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened...")

  @commands.group(
    name="cmd",
    brief="Adds custom commands",
    invoke_without_command=True,
    case_insensitive=True
  )
  @can_edit_commands()
  async def _cmd(self, context):
    await context.send_help("cmd")

  @_cmd.command(
    name="add",
    brief="Adds a command to the bot.",
    help="Adds a new permanent command to the bot. The command will send the text, when ?name is invoked. String key-value pairs are supported and will be passed to the command, but name attribute will be ignored. You MUST add a new line between the key-value pairs, and MUST NOT add a new line inside the key-value pairs (except cmd_text), the last key MUST be cmd_text which is the text sent by the command.",
    usage="<cmd_name> [attribute=value]... [cmd_text=value]"
  )
  @can_edit_commands()
  async def _add_cmd(self, context, cmd_name:cmd_name_converter, *, cmd_args:cmd_add_converter):
    attributes, cmd_text = cmd_args
    if not cmd_text:
      raise commands.UserInputError("Unexpected format, no text found for the command")
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, False)
    set_new_cmd(parent, child, cmd_text, attributes, False)
    await self.after_cmd_update(context, cmd_name, cmd_text, attributes, False, "Added Command")
    
  @_cmd.command(
    name="gadd",
    brief="Adds a command group to the bot.",
    help="Adds a new permanent command group to the bot. The command will send the text or send the help if text is empty, when ?name is invoked. String key-value pairs are supported and will be passed to the command, but name attribute will be ignored. You MUST add a new line between the key-value pairs, and MUST NOT add a new line inside the key-value pairs (except cmd_text), the last key MUST be cmd_text which is the text sent by the command.",
    usage="<cmd_name> [attribute=value]... [cmd_text=value]"
  )
  @can_edit_commands()
  async def _gadd_cmd(self, context, cmd_name:cmd_name_converter, *, cmd_args:cmd_add_converter=None):
    if cmd_args is None:
      attributes = {}
      cmd_text = ""
    else:
      attributes, cmd_text = cmd_args
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, False)
    set_new_cmd(parent, child, cmd_text, attributes, True)
    await self.after_cmd_update(context, cmd_name, cmd_text, attributes, True, "Added Command Group")
    
  @_cmd.command(
    name="rename",
    brief="Remane a custom command of the bot.",
  )
  @can_edit_commands()
  async def _rename_cmd(self, context, cmd_name:cmd_name_converter, new_name:cmd_name_converter):
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True)
    new_parent, new_child, new_name = get_cmd_attributes(self.bot, new_name, False)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      if cmd["lock"]:
        raise LookupError(f"Custom command '{cmd_name}' is locked and canot be edited.")
      attributes = json_load_dict(cmd["attributes"])
      old_cmd = parent.remove_command(child)
      try:
        new_cmd = set_new_cmd(new_parent, new_child, cmd["message"], attributes, cmd["isgroup"])
        # move the commands
        if isinstance(old_cmd, commands.Group) and isinstance(new_cmd, commands.Group):
          for command in old_cmd.commands: # move the commands from the old one to the new one
            new_cmd.add_command(command)
            self.bot.db[context.guild.id].query(f"UPDATE user_commands SET cmdname='{new_name} {command.name}' WHERE cmdname='{cmd_name} {command.name}'")
        self.bot.db[context.guild.id].query(f"UPDATE user_commands SET cmdname='{new_name}' WHERE cmdname='{cmd_name}' ")
        await self.log_cmd_update(context, new_name, cmd["message"], attributes, cmd["isgroup"], "Renamed Command")
      except Exception as e:
        parent.add_command(old_cmd)
        raise e
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")

  @_cmd.command(
    name="edit",
    brief="Updates a custom command of the bot.",
    aliases=["update"],
    usage="<cmd_name> [attribute=value]... [cmd_text=value]"
  )
  @can_edit_commands()
  async def _update_cmd(self, context, cmd_name:cmd_name_converter, *, cmd_args:cmd_add_converter):
    attributes_new, cmd_text = cmd_args
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      if cmd["lock"]:
        raise LookupError(f"Custom command '{cmd_name}' is locked and canot be edited.")
      if not cmd_text and not cmd["isgroup"]:
        cmd_text = cmd["message"]
      attributes = json_load_dict(cmd["attributes"])
      attributes.update(attributes_new)
      set_new_cmd(parent, child, cmd_text, attributes, cmd["isgroup"])
      await self.after_cmd_update(context, cmd_name, cmd_text, attributes, cmd["isgroup"], "Updated Command")
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")

  @_cmd.command(
    name="rm",
    brief="Removes a command from the bot.",
    aliases=["delete", "del"]
  )
  @can_edit_commands()
  async def _rm_cmd(self, context, cmd_name:cmd_name_converter):
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True, True)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      if cmd["lock"]:
        raise LookupError(f"Custom command '{cmd_name}' is locked and canot be edited.")
      # check the child commands
      if cmd["isgroup"]:
        childs = self.bot.db[context.guild.id].query(f"SELECT * FROM user_commands WHERE cmdname LIKE '{cmd_name} %'")
        if len(childs) > 0:
          raise LookupError(f"Custom command '{cmd_name}' cannot be removed because it has at least one child in db.")
      parent.remove_command(child)
      self.bot.db[context.guild.id].delete_row("user_commands", cmd_name)
      await self.log_cmd_update(context, cmd_name, cmd["message"], {}, cmd["isgroup"], "Removed Command")
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")

  @_cmd.command(
    name="alias",
    brief="Adds aliases to a command.",
    aliases=["aliases","als"]
  )
  @can_edit_commands()
  async def _alias_cmd(self, context, cmd_name:cmd_name_converter, *aliases):
    if len(aliases) == 0:
      raise commands.UserInputError("aliases is a required argument that is missing.")
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      if cmd["lock"]:
        raise LookupError(f"Custom command '{cmd_name}' is locked and canot be edited.")
      attributes = json_load_dict(cmd["attributes"])
      if "aliases" not in attributes:
        attributes["aliases"] = []
      attributes["aliases"].extend(aliases)
      set_new_cmd(parent, child, cmd["message"], attributes, cmd["isgroup"])
      await self.after_cmd_update(context, cmd_name, cmd["message"], attributes, cmd["isgroup"], "Added Aliases")
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")
      
  @_cmd.command(
    name="lock",
    brief="Locks a command.",
  )
  @has_admin_role()
  async def _lock_cmd(self, context, cmd_name:cmd_name_converter):
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      self.bot.db[context.guild.id].query(f"UPDATE user_commands SET lock=1 WHERE cmdname='{cmd_name}'")
      await context.send(f"Command '{cmd_name}' has been locked.")
      title = f"User Locked a Command"
      fields = {"User":f"{context.author.mention}\n{context.author}",
                "Command Group" if cmd["isgroup"] else "Command":cmd_name}
      await self.bot.log_admin(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")
      
  @_cmd.command(
    name="unlock",
    brief="Unlocks a command.",
  )
  @has_admin_role()
  async def _unlock_cmd(self, context, cmd_name:cmd_name_converter):
    parent, child, cmd_name = get_cmd_attributes(self.bot, cmd_name, True)
    cmd = self.bot.db[context.guild.id].select("user_commands", cmd_name)
    if cmd is not None:
      self.bot.db[context.guild.id].query(f"UPDATE user_commands SET lock=0 WHERE cmdname='{cmd_name}'")
      await context.send(f"Command '{cmd_name}' has been unlocked.")
      title = f"User Unlocked a Command"
      fields = {"User":f"{context.author.mention}\n{context.author}",
                "Command Group" if cmd["isgroup"] else "Command":cmd_name}
      await self.bot.log_admin(context.guild, title=title, fields=fields, timestamp=context.message.created_at)
    else:
      raise LookupError(f"Custom command '{cmd_name}' not found.")

  async def after_cmd_update(self, context, cmd_name, cmd_text, attributes, isgroup, action):
    self.bot.db[context.guild.id].insert_or_update("user_commands", cmd_name, cmd_text, json.dumps(attributes), int(isgroup), 0)
    await self.log_cmd_update(context, cmd_name, cmd_text, attributes, isgroup, action)
    
    
  async def log_cmd_update(self, context, cmd_name, cmd_text, attributes, isgroup, action):
    await context.send(f"{action}: '{cmd_name}'.")
    title = f"User {action}"
    fields = {"User":f"{context.author.mention}\n{context.author}",
              "Command Group" if isgroup else "Command":cmd_name,
              "Content":cmd_text[:1021] + '...' if cmd_text and len(cmd_text) > 1021 else cmd_text,
              "Attributes":"\n".join([f"{k}={v}" for k,v in attributes.items()]) if attributes else None}
    await self.bot.log_admin(context.guild, title=title, fields=fields, timestamp=context.message.created_at)

#This function is needed for the load_extension routine.
def setup(bot):
  bot.add_cog(CommandCog(bot))
  print("Added command cog.")
