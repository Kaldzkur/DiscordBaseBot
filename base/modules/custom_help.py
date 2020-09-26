from discord.ext import commands
import operator

class CategoryHelpCommand(commands.DefaultHelpCommand):
  # A customized help command class
  # One can input a dict: cog name -> category name
  # Then the help command will shows all the commands of the key cogs under the mapped categories
  # The commands of other cogs will still be under the default cog category
  def __init__(self, categoryMap=None, customCategory="Custom Commands", sort_cogs=False, **options):
    super().__init__(**options)
    if categoryMap is None:
      self.categoryMap = {}
    else:
      self.categoryMap = categoryMap
    self.customCategory = customCategory
    self.sort_cogs = sort_cogs
      
  async def send_bot_help(self, mapping):
    commandMapping = {} # a new command mapping, category str -> command list
    max_len = 0
    # filter and re-categorize the commands
    for cog, commandList in mapping.items():
      if cog is None: # do not process commands without a cog first
        continue
      filtered_commands = await self.filter_commands(commandList)
      if len(filtered_commands) == 0:
        continue
      max_len = max(max_len, max(len(command.name) for command in filtered_commands))
      if cog.qualified_name in self.categoryMap:
        category = self.categoryMap[cog.qualified_name]
      else:
        category = cog.qualified_name
      if category not in commandMapping:
        commandMapping[category] = []
      commandMapping[category].extend(filtered_commands)
    # move the commands in "No Category" into self.customCategory
    if None in mapping:
      filtered_commands = await self.filter_commands(mapping[None])
      if len(filtered_commands) > 0:
        max_len = max(max_len, max(len(command.name) for command in filtered_commands))
        noCategoryList = set()
        customList = set()
        for command in filtered_commands:
          if command.name != "help":
            customList.add(command)
          else:
            noCategoryList.add(command)
        if len(customList) > 0:
          if self.customCategory not in commandMapping:
            commandMapping[self.customCategory] = []
          commandMapping[self.customCategory].extend(customList)
        if len(noCategoryList) > 0:
          commandMapping[None] = list(noCategoryList)
    # sort the commands in mapping
    if self.sort_commands:
      for category in commandMapping:
        commandMapping[category].sort(key=operator.attrgetter('name'))
    msg = ""
    for category in (sorted(commandMapping, key=lambda x: (x is None, x)) if self.sort_cogs else commandMapping):
      if len(commandMapping[category]) == 0:
        continue
      msg = await self.smart_append_msg(msg, f"{category if category else self.no_category}:")
      for command in commandMapping[category]:
        msg = await self.smart_append_msg(msg, f"{'':<{self.indent}}{command.name:<{max_len}} {command.short_doc}")
    msg = await self.smart_append_msg(msg, "") # empty line
    msg = await self.smart_append_msg(msg, f"Type {self.context.prefix}help command for more info on a command.")
    msg = await self.smart_append_msg(msg, f"You can also type {self.context.prefix}help category for more info on a category.")
    await self.send_code_block(msg)
    
  async def smart_append_msg(self, msg, new_msg):
    # send msg out and return new_msg if msg + '\n' + new_msg is longer than 2000
    # else, return the appended message
    if len(msg) + len(new_msg) > 2000-7: # split the message if too long
      await self.send_code_block(msg)
      return new_msg
    else:
      return f"{msg}\n{new_msg}"
      
  async def send_code_block(self, msg):
    await self.get_destination().send(f"```{msg}```")
