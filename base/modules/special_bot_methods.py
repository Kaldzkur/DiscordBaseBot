import discord
from discord.ext import commands
from discord.ext.commands.view import StringView
from discord.ext.commands.context import Context

async def special_get_context(bot, message, cmdtext, *, cls=Context):
  # similar to bot's get_context method but use cmdtext rather than message.content to build the context
  # notice that if any command uses context.message.content be behavior may not be as expected
  # the documentation can be viewed in discord.ext.commands -> bot.get_context
  
  view = StringView(cmdtext)
  ctx = cls(prefix=None, view=view, bot=bot, message=message)

  if bot._skip_check(message.author.id, bot.user.id):
    return ctx

  prefix = await bot.get_prefix(message)
  invoked_prefix = prefix

  if isinstance(prefix, str):
    if not view.skip_string(prefix):
      return ctx
  else:
    try:
      # if the context class' __init__ consumes something from the view this
      # will be wrong.  That seems unreasonable though.
      if cmdtext.startswith(tuple(prefix)):
        invoked_prefix = discord.utils.find(view.skip_string, prefix)
      else:
        return ctx

    except TypeError:
      if not isinstance(prefix, list):
         raise TypeError("get_prefix must return either a string or a list of string, "
                         "not {}".format(prefix.__class__.__name__))

       # It's possible a bad command_prefix got us here.
      for value in prefix:
        if not isinstance(value, str):
          raise TypeError("Iterable command_prefix or list returned from get_prefix must "
                          "contain only strings, not {}".format(value.__class__.__name__))

      # Getting here shouldn't happen
      raise

  invoker = view.get_word()
  ctx.invoked_with = invoker
  ctx.prefix = invoked_prefix
  ctx.command = bot.all_commands.get(invoker)
  return ctx
  
async def special_process_command(bot, message, cmdtext):
  if message.author.bot:
    return
  ctx = await special_get_context(bot, message, cmdtext)
  await bot.invoke(ctx)
  
async def command_check(bot, message, cmdtext):
  # try to parse the command to check the validity, this will raise CommandNotFound or CheckFailure
  ctx = await special_get_context(bot, message, cmdtext)
  if ctx.command is not None:
    if await bot.can_run(ctx, call_once=True):
      await command_class_check(ctx.command, ctx)
    else:
      raise commands.CheckFailure('The global check once functions failed.')
  elif ctx.invoked_with:
    raise commands.CommandNotFound(f'Command "{ctx.invoked_with}" is not found.')
  else:
    raise commands.CommandNotFound('There is no command to excute.')
    
async def command_class_check(command, ctx):
  if isinstance(command, commands.Group):
    await command_group_check(command, ctx)
  elif isinstance(command, commands.Command):
    await command_regular_check(command, ctx)
  else:
    raise commands.CommandNotFound('There is no command to excute.')
    
async def command_regular_check(command, ctx):
  if not await command.can_run(ctx):
    raise CheckFailure(f'The check functions for command {command.qualified_name} failed.')
  await command._parse_arguments(ctx) # will raise converting error inside
  # notice that the concurrency and cooldown will not be checked here
  
async def command_group_check(command, ctx):
  ctx.invoked_subcommand = None
  ctx.subcommand_passed = None
  early_invoke = not command.invoke_without_command
  if early_invoke:
    await command_regular_check(command, ctx)

  view = ctx.view
  previous = view.index
  view.skip_ws()
  trigger = view.get_word()

  if trigger:
    ctx.subcommand_passed = trigger
    ctx.invoked_subcommand = command.all_commands.get(trigger, None)

  if trigger and ctx.invoked_subcommand:
    ctx.invoked_with = trigger
    await command_class_check(ctx.invoked_subcommand, ctx)
  elif not early_invoke:
    view.index = previous
    view.previous = previous
    await command_regular_check(command, ctx)
