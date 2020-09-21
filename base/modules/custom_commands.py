import discord
from discord.ext import commands
from pytz import timezone
import operator
import json
from base.modules.access_checks import has_admin_role, has_mod_role
from base.modules.basic_converter import smart_clean_content

def json_load_dict(string):
  if string:
    try:
      dic = json.loads(string)
      if not isinstance(dic, dict):
        dic = {}
    except:
      dic = {}
  else:
    dic = {}
  return dic
  
def server_check_fun(guild):
  def server_check(context):
    return context.guild == guild if guild else True
  return commands.check(server_check)

def permission_check_fun(permission):
  if permission <= 0:
    return commands.check(lambda context: True)
  elif permission == 1:
    return has_mod_role()
  elif permission == 2:
    return has_admin_role()
  else:
    return commands.is_owner()

def get_cmd_parent_child(root, cmd_name):
  cmd_name_split = cmd_name.split(maxsplit=1)
  if len(cmd_name_split) == 1:
    return (root, cmd_name)
  else:
    parent = cmd_name_split[0]
    child = cmd_name_split[1]
    parent_cmd = root.get_command(parent)
    if parent_cmd is None:
      raise NameError(f"Command '{cmd_name}' is invalid because its parent command "
        f"'{root.qualified_name+' ' if hasattr(root, 'qualified_name') else ''}{parent}' does not exists.")
    if not isinstance(parent_cmd, commands.Group):
      raise NameError(f"Command '{cmd_name}' is invalid because its parent command "
        f"'{parent_cmd.qualified_name}' is not a command group.")
    return get_cmd_parent_child(parent_cmd, child)
  
async def analyze_existing_cmd(bot, guild, cmd_name, context=None, remove=False):
  parent, child = get_cmd_parent_child(bot, cmd_name)
  if parent != bot: # check whether the parent command is a valid custom command in guild db
    parent_cmd = bot.db[guild.id].select("user_commands", parent.qualified_name)
    if parent_cmd is None or not parent_cmd["isgroup"]:
      raise NameError(f"Command '{cmd_name}' is invalid because '{parent.qualified_name}' is not a custom command group in this server.")
  existing_cmd = parent.get_command(child)
  if existing_cmd is None:
    raise NameError(f"Command '{cmd_name}' does not exist.")
  if context and not await existing_cmd.can_run(context):
    raise NameError(f"You do not have the permission to run command '{existing_cmd.qualified_name}'.")
  if remove and isinstance(existing_cmd, commands.Group) and len(existing_cmd.commands) > 0:
    raise LookupError(f"Command '{cmd_name}' cannot be removed because it has at least one child command.")
  cmd_name = existing_cmd.qualified_name
  cmd = bot.db[guild.id].select("user_commands", cmd_name)
  if cmd is None:
    raise NameError(f"Command '{cmd_name}' is not a custom command in this server.")
  # check the child commands
  if remove and cmd["isgroup"]:
    childs = bot.db[guild.id].query(f"SELECT * FROM user_commands WHERE cmdname LIKE '{cmd_name} %'")
    if len(childs) > 0:
      raise LookupError(f"Custom command '{cmd_name}' cannot be removed because it has at least one child in db.")
  return (parent, existing_cmd.name, cmd)
  
async def analyze_new_cmd(bot, guild, cmd_name, context=None):
  parent, child = get_cmd_parent_child(bot, cmd_name)
  if parent != bot: # check whether the parent command is a valid custom command in guild db
    if context and not await parent.can_run(context):
      raise NameError(f"You do not have the permission to run parent command '{parent.qualified_name}'.")
    parent_cmd = bot.db[guild.id].select("user_commands", parent.qualified_name)
    if parent_cmd is None or not parent_cmd["isgroup"]:
      raise NameError(f"Command '{cmd_name}' is invalid because {parent.qualified_name} is not a custom command group in this server.")
    cmd_name = f"{parent.qualified_name} child"
  existing_cmd = parent.get_command(child)
  if existing_cmd is not None:
    raise NameError(f"Command '{cmd_name}' already exists.")
  return (parent, child, f"{parent.qualified_name} {child}" if hasattr(parent, "qualified_name") else child)
     
def make_user_command(guild, cmd_name, cmd_text, permission=0, **attributes):
  @commands.command(
    name=cmd_name
  )
  @server_check_fun(guild)
  @permission_check_fun(permission)
  async def _wrapper_user_cmd(context, args:commands.Greedy[smart_clean_content]):
    await context.send(cmd_text.format(*args))
  @_wrapper_user_cmd.error
  async def _wrapper_user_cmd_error(context, error):
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to use this command in this server.")
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, IndexError):
      await context.send(f"{context.author.mention} you do not have enough arguments to the command `?{context.command.qualified_name}`.")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while excuting this command.")
  _wrapper_user_cmd.update(**attributes)
  return _wrapper_user_cmd
    
def make_user_group(guild, cmd_name, cmd_text, permission=0, **attributes):
  @commands.group(
    name=cmd_name,
    invoke_without_command=True,
    case_insensitive=True
  )
  @server_check_fun(guild)
  @permission_check_fun(permission)
  async def _wrapper_user_cmd(context, args:commands.Greedy[smart_clean_content]):
    if cmd_text:
      await context.send(cmd_text.format(*args))
    else:
      await context.send_help(context.command)
  @_wrapper_user_cmd.error
  async def _wrapper_user_cmd_error(context, error):
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to use this command in this server.")
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, IndexError):
      await context.send(f"{context.author.mention} you do not have enough arguments to the command `?{context.command.qualified_name}`.")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while excuting this command.")
  _wrapper_user_cmd.update(**attributes)
  return _wrapper_user_cmd
  
def fix_aliases(parent, child_name, aliases):
  # fix the aliases of a command to remove any duplicates
  if parent.case_insensitive:
    new_aliases = [alias.lower() for alias in aliases]
  else:
    new_aliases = aliases
  new_aliases = list(set(new_aliases))
  new_aliases = [alias for alias in new_aliases if (parent.get_command(alias) is None and alias != child_name)]
  return new_aliases
  
def smart_add_command(parent, cmd):
  # add the command smartly to remove duplicates of aliases
  new_aliases = fix_aliases(parent, cmd.name, cmd.aliases)
  cmd.update(aliases=new_aliases)
  parent.add_command(cmd)

def check_aliases(parent, child_name, aliases):
  # child_name is the name of the child to be updated, which will be ignored
  if parent.case_insensitive:
    aliases = [alias.lower() for alias in aliases]
  aliases_set = set()
  for alias in aliases:
    cmd = parent.get_command(alias)
    if cmd is not None and (cmd.name != child_name or cmd.name == alias):
      raise commands.CommandRegistrationError(alias, alias_conflict=True)
    if alias in aliases_set:
        raise commands.CommandRegistrationError(alias, alias_conflict=True)
    else:
        aliases_set.add(alias)
      
def move_subcommands(old_cmd, new_cmd):
  if isinstance(old_cmd, commands.Group) and isinstance(new_cmd, commands.Group):
    for command in old_cmd.commands: # move the commands from the old one to the new one
      if (not old_cmd.case_insensitive) and new_cmd.case_insensitive:
        # if case_insensitive has changed to False, fix the aliases of subcommands by using smart add
        smart_add_command(new_cmd, command)
      else:
        new_cmd.add_command(command)

def set_new_cmd(guild, parent, child_name, cmd_text, attributes, is_group=False, permission=0, smart_fix=False):
  # check aliases here
  if "aliases" in attributes:
    if smart_fix:
      attributes["aliases"] = fix_aliases(parent, child_name, attributes["aliases"])
    # make sure the aliases are unique
    else:
      check_aliases(parent, child_name, attributes["aliases"])
  old_cmd = parent.remove_command(child_name) # remove the command if exits, it doesn't hurt if the command does not exist
  if is_group:
    usr_command = make_user_group(guild, child_name, cmd_text, permission, **attributes)
  else:
    usr_command = make_user_command(guild, child_name, cmd_text, permission, **attributes)
  parent.add_command(usr_command)
  move_subcommands(old_cmd, usr_command)
  return usr_command
  
async def add_cmd_from_row(bot, guild, cmd):
  attributes = json_load_dict(cmd["attributes"])
  parent, child, cmd_name = await analyze_new_cmd(bot, guild, cmd["cmdname"])
  if cmd["glob"]:
    guild = None
  return set_new_cmd(guild, parent, child, cmd["message"], attributes, cmd["isgroup"], cmd["perm"])
  
async def add_cmd_from_attributes(context, cmd_name, cmd_msg, attributes, isgroup):
  parent, child, cmd_name = await analyze_new_cmd(context.bot, context.guild, cmd_name, context)
  return set_new_cmd(context.guild, parent, child, cmd_msg, attributes, isgroup)
  
