from datetime import datetime
import operator
import math
import discord
from discord.ext import commands
from base.modules.interactive_message import InteractiveMessage
from base.modules.constants import arrow_emojis, num_emojis

def get_cmd_help_string_short(command, help_cmd=None):
  cmd_str = [f"`{command.name}"]
  if len(command.aliases) > 0 and (help_cmd and help_cmd.show_aliases or not help_cmd):
    cmd_str.append("".join([f"/{alias}" for alias in command.aliases]))
  if command.short_doc:
    cmd_str.append(f":` {command.short_doc}")
  else:
    cmd_str.append("`")
  return "".join(cmd_str)

async def get_cmd_help_string(command, prefix, page=None, display_all_subcommands=False, help_cmd=None):
  cmd_str = []
  if command.description:
    cmd_str.append(f"{command.description}\n\n")
  if len(command.aliases) > 0:# and (help_cmd and help_cmd.show_aliases or not help_cmd):
    cmd_str.append(f"\nExample:\n`{prefix}[{command.qualified_name}")
    cmd_str.append("".join([f"|{alias}" for alias in command.aliases]))
    cmd_str.append("]")
  else:
    cmd_str.append(f"\nExample:\n`{prefix}{command.qualified_name}")
  if isinstance(command, commands.Group):
    signature = command.signature
    if signature:
      cmd_str.append(f" {signature}`")
    else:
      cmd_str.append(f" <command>`")
    cmd_str.append("\nCommands:\n")
    len_num = len(num_emojis)
    filtered_sub_cmds = await help_cmd.filter_commands(command.commands, sort=help_cmd.sort_commands) if help_cmd else command.commands
    len_orig_subs = len(filtered_sub_cmds)
    if not display_all_subcommands:
      _idx = page*len_num
      filtered_sub_cmds = filtered_sub_cmds[_idx:_idx+len_num]
    for i, subcommand in enumerate(filtered_sub_cmds):
      if page is not None:
        if display_all_subcommands:
          i = i-len_num*page
          if 0 <= i < len_num:
            cmd_str.append(f"{num_emojis[i]} {get_cmd_help_string_short(subcommand, help_cmd)}\n")
          else:
            cmd_str.append(f" {get_cmd_help_string_short(subcommand, help_cmd)}\n")
        else:
          cmd_str.append(f"{num_emojis[i]} {get_cmd_help_string_short(subcommand, help_cmd)}\n")
      else:
        cmd_str.append(f" {get_cmd_help_string_short(subcommand, help_cmd)}\n")
    if (not display_all_subcommands and page is not None and len_orig_subs > len(filtered_sub_cmds)
        and math.ceil(float(len_orig_subs)/len_num) -1 != page):
      #if no last page
      cmd_str.append(f"To see more subcommands use {arrow_emojis['forward']}.\n")
    cmd_str.append(f"For more information use `{prefix}help {command.qualified_name} <command>`.")
  else:
    signature = command.signature
    if signature:
      cmd_str.append(f" {signature}`")
    else:
      cmd_str.append("`")
  if command.help:
    cmd_str.append(f"\n\n{command.help.format(prefix=prefix)}")
  return "".join(cmd_str)

class InteractiveHelpCommand(commands.HelpCommand):

  def __init__(self, category_mappings, no_category="Server Specific", show_aliases=False, sort_commands=True, *args, **options):
    super().__init__(**options)
    #category_mappings = [{"Admin Commands":["Cog1", "Cog2"]}]
    self.category_mappings = category_mappings
    self.no_category = no_category
    self.show_aliases = show_aliases
    self.sort_commands = sort_commands

  async def _create_page_mapping(self, mapping):
    #{"Administraction":[command_list]}
    page_mapping = {}
    no_category_cmds = set()
    for cog, cmd_list in mapping.items():
      commands = await self.filter_commands(cmd_list)
      if len(commands) == 0:
        continue
      if cog is not None:
        for name, cog_list in self.category_mappings.items():
          if cog.qualified_name in cog_list:
            if name not in page_mapping:
              page_mapping[name] = []
            page_mapping[name] += commands
            break
        else: # no category
          if cog.qualified_name not in page_mapping:
            page_mapping[cog.qualified_name] = []
          page_mapping[cog.qualified_name] += commands
      else: # no category
        for cmd in commands:
          if cmd.name != "help": # ignore help command
            no_category_cmds.add(cmd)
    if no_category_cmds:
      if self.no_category not in page_mapping:
        page_mapping[self.no_category] = []
      page_mapping[self.no_category] += list(no_category_cmds)
    if self.sort_commands:
      for category in page_mapping:
        page_mapping[category].sort(key=operator.attrgetter('name'))
    return page_mapping    

  async def send_bot_help(self, mapping):
    mapping = await self._create_page_mapping(mapping)
    timeout = self.context.bot.get_setting(self.context.guild, "ACTIVE_TIME") * 60
    await InteractiveHelpRoot(self, mapping, context=self.context, timeout=timeout).start()
    
  async def send_cog_help(self, cog):
    #This function is called with cogname
    pass
    
  async def send_group_help(self, group):
    #if not await self.filter_commands([group]):
    #  await self.get_destination().send(f"Sorry but you do not have the permission to use this command.")
    #  return
    subcommands = await self.filter_commands(group.commands, sort=self.sort_commands)
    timeout = self.context.bot.get_setting(self.context.guild, "ACTIVE_TIME") * 60
    await InteractiveHelpGroup(self, group, subcommands, 0, context=self.context, timeout=timeout).start()
    
  async def send_command_help(self, command):
    #if not await self.filter_commands([command]):
    #  await self.get_destination().send(f"Sorry but you do not have the permission to use this command.")
    #  return
    timeout = self.context.bot.get_setting(self.context.guild, "ACTIVE_TIME") * 60
    await InteractiveHelpGroup(self, command, [], 0, context=self.context, timeout=timeout).start()

class InteractiveHelpRoot(InteractiveMessage):

  def __init__(self, help_cmd, page_mapping, page_num=1, parent=None, **attributes):
    super().__init__(parent, **attributes)
    self.help_cmd = help_cmd
    self.page_mapping = page_mapping
    self.page_num = page_num
    self.update_child_emojis()
  
  def update_child_emojis(self):
    self.child_emojis = [arrow_emojis["backward"]]
    total_page = len(self.page_mapping) + 1
    page_selection = 10 if (total_page//10 > (self.page_num-1)//10) else (total_page % 10)
    self.child_emojis += [num_emojis[i] for i in range(1, page_selection+1)]
    self.child_emojis.append(arrow_emojis["forward"])


  async def transfer_to_child(self, emoji):
    if emoji == arrow_emojis["backward"]:
      new_page = max(self.page_num-1, 1)
    elif emoji == arrow_emojis["forward"]:
      new_page = min(self.page_num+1, len(self.page_mapping)+1)
    else:
      num = num_emojis.index(emoji)
      new_page = (self.page_num-1)//10 * 10 + num
    if self.page_num == new_page:
      return None
    self.page_num = new_page
    self.update_child_emojis()
    return self
    

  async def get_embed(self):
    if self.page_num == 1: # table of contents
      description = f"{self.context.bot.user.name} is a multipurpose discord bot that can be extended for each server individually.\nUse the emojis to switch between pages."
      embed = discord.Embed(title=f"{self.context.bot.user.name} Help", timestamp=datetime.utcnow(), description=description)
      page_num, pages = 2, []
      pages.append("Page 1: Table of Contents")
      for page in self.page_mapping:
        if page is None:
          page = self.help_cmd.no_category
        pages.append(f"Page {page_num}: {page}")
        page_num += 1
      embed.add_field(name="Help Pages:", value="\n".join(pages))
      embed.set_footer(text=f"Page 1/{len(pages)}")
      return embed
    else: # command page
      description = []
      index = self.page_num - 2
      name = list(self.page_mapping)[index]
      commands = self.page_mapping[name]
      for command in commands:
        description.append(get_cmd_help_string_short(command, self.help_cmd))
      embed = discord.Embed(
        title=f"{name} Help" if name is not None else self.help_cmd.no_category,
        timestamp=datetime.utcnow(),
        description="\n".join(description)
      )
      embed.set_footer(text=f"Page {self.page_num}/{len(self.page_mapping)+1}")
      return embed

class InteractiveHelpPage(InteractiveMessage):

  def __init__(self, help_cmd, page_mapping, page_number, parent=None, **attributes):
    super().__init__(parent, **attributes)
    self.help_cmd = help_cmd
    self.page_mapping = page_mapping
    self.page_number = page_number
    if page_number > 0:
      self.child_emojis.append(arrow_emojis["backward"])
    if page_number < len(self.page_mapping)-1:
      self.child_emojis.append(arrow_emojis["forward"])
      
  async def transfer_to_child(self, emoji):
    if emoji == arrow_emojis["forward"]:
      self.page_number += 1
    elif emoji == arrow_emojis["backward"]:
      self.page_number -= 1
    return InteractiveHelpPage(self.help_cmd, self.page_mapping, self.page_number, self.parent)

  async def get_embed(self):
    description = []
    for i, (name, commands) in enumerate(self.page_mapping.items()):
      if i == self.page_number:
         break
    else:
      raise ValueError(f"Page {self.page_number} not found.")
    for command in commands:
      description.append(get_cmd_help_string_short(command, self.help_cmd))
    embed = discord.Embed(
      title=f"{name} Help" if name is not None else self.help_cmd.no_category,
      timestamp=datetime.utcnow(),
      description="\n".join(description)
    )
    embed.set_footer(text=f"Page {self.page_number+2}/{len(self.page_mapping)+1}")
    return embed
  
class InteractiveHelpGroup(InteractiveMessage):

  def __init__(self, help_cmd, group, subcommands=None, page_number=0, parent=None, **attributes):
    super().__init__(parent, **attributes)
    self.help_cmd = help_cmd
    self.group = group
    if subcommands is None:
      self.subcommands = []
    else:
      self.subcommands = subcommands
    self.page_number = page_number
    self.get_child_emojis()
        
  def get_child_emojis(self): # update the child emojis based on page number
    len_subs, len_nums = len(self.subcommands), len(num_emojis)
    if 0 < len_subs <= len_nums:
      self.child_emojis = num_emojis[0:len_subs]
    elif len_subs > 0:
      if self.page_number > 0:
        self.child_emojis = [arrow_emojis["backward"]]
        self.child_emojis += num_emojis[0:len_subs-len_nums*self.page_number]
      else:
        self.child_emojis = num_emojis[0:]
      if math.ceil(float(len_subs) / len_nums) -1 != self.page_number:
        self.child_emojis.append(arrow_emojis["forward"])

  async def transfer_to_child(self, emoji):
    if emoji == arrow_emojis["forward"]:
      self.page_number += 1
      self.get_child_emojis()
      return self
    elif emoji == arrow_emojis["backward"]:
      self.page_number -= 1
      self.get_child_emojis()
      return self
    elif emoji in num_emojis:
      for i, e in enumerate(num_emojis):
        if emoji == e:
          break
      command = self.subcommands[self.page_number*len(num_emojis) + i]
      if isinstance(command, commands.Group):
        subcommands = await self.help_cmd.filter_commands(command.commands, sort=self.help_cmd.sort_commands)
        return InteractiveHelpGroup(self.help_cmd, command, subcommands, 0, self)
      else:
        return InteractiveHelpGroup(self.help_cmd, command, [], 0, self)

  '''
  #Override accept_emojis
  @property
  def accept_emojis(self):
    if (isinstance(self.group, commands.Group)
       and self.parent is not None and self.parent.group == self. group
       and self.page_number == 0 and arrow_emojis["backward"] in super().accept_emojis):
      #When we have a group command and are on page 0, we do not want the back emoji.
      tmp = super().accept_emojis
      tmp.remove(arrow_emojis["backward"])
      return tmp
    else:
      return super().accept_emojis
  '''

  async def get_embed(self):
    prefix = self.context.bot.get_guild_prefix(self.context.guild) if self.context.guild else self.context.prefix
    description = await get_cmd_help_string(self.group, prefix, self.page_number, help_cmd=self.help_cmd)
    if isinstance(self.group, commands.Group):
      embed = discord.Embed(title=f"Group `{self.group.qualified_name}` Help", description=description)
    else:
      embed = discord.Embed(title=f"Command `{self.group.qualified_name}` Help", description=description)
    return embed
