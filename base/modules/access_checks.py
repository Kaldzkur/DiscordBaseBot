from discord.ext import commands

def is_server_owner():
  async def predicate(context):
    return context.author.id == context.guild.owner_id
  return commands.check(predicate)
  
def admin_role_check(context):
  if context.author.id in context.bot.owner_ids:
    return True
  admin_role = context.bot.get_admin_role(context.guild)
  if admin_role is None:
    return False
  else:
    if admin_role in context.author.roles:
      return True
    raise commands.MissingRole(admin_role)

def has_admin_role():
  return commands.check(admin_role_check)

def mod_role_check(context):
  if context.author.id in context.bot.owner_ids:
    return True
  mod_role = context.bot.get_mod_role(context.guild)
  if mod_role is None:
    return False
  else:
    if mod_role in context.author.roles:
      return True
    raise commands.MissingRole(admin_role)
  
def has_mod_role():
  return commands.check(mod_role_check)
  
def is_one_of_members(*member_ids):
  def member_check(context):
    return context.author.id in member_ids
  return commands.check(member_check)
  
def can_edit_commands():
  async def predicate(context):
    if context.author.id in context.bot.owner_ids:
      return True
    admin_role = context.bot.get_admin_role(context.guild)
    cmd_role = context.bot.get_cmd_role(context.guild)
    if admin_role is None and cmd_role is None:
      return False
    else:
      if admin_role in context.author.roles or cmd_role in context.author.roles:
        return True
      raise commands.MissingRole(cmd_role)
  return commands.check(predicate)

def check_channel_permissions(channel, author, permissions):
  user_permissions = channel.permissions_for(author)
  for permission in permissions:
    if not getattr(user_permissions, permission, False):
      raise commands.MissingPermissions(permissions)
  return True
