import os
import shutil
import time
import discord
from discord.ext import commands
from base.modules.access_checks import has_admin_role
from base.modules.constants import DB_PATH as path

#An extension for hero commands.
class DatabaseManagementCog(commands.Cog, name="Database Commands"):
  def __init__(self, bot):
    self.bot = bot

  async def cog_command_error(self, context, error):
    if hasattr(context.command, "on_error"):
      # This prevents any commands with local handlers being handled here.
      return
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to manipulate the database.")
    elif isinstance(error, commands.CommandInvokeError):
      if (isinstance(error.original, NameError) or isinstance(error.original, RuntimeError) or
          isinstance(error.original, KeyError) or isinstance(error.original, LookupError) or
          isinstance(error.original, TypeError) or isinstance(error.original, IndexError)):
        await context.send(f"Sorry {context.author.mention}, but there is a lookup error: {error.original}")
      elif isinstance(error.original, FileNotFoundError) or isinstance(error.original, IOError):
        await context.send(f"Sorry {context.author.mention}, I could not export the tables because {error.original}")
      else:
        await context.send(f"Sorry {context.author.mention}, but {error.original}")
    elif isinstance(error, commands.UserInputError):
      await context.send(f"Sorry {context.author.mention}, but I could not understand the arguments passed to `{context.prefix}{context.command.qualified_name}`.")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while modifying the database.")

  @commands.group(
    name="db",
    brief="Manipulates database",
    usage="<command>",
    case_insensitive = True,
    invoke_without_command=True
  )
  @has_admin_role()
  async def _db(self, context):
    await context.send_help("db")

  @_db.command(
    name="createtable",
    brief="Creates a new table.",
    help="Parameters:\n name - the name of the table\n primary_key - the PRIMARY KEY of the table(mandatory)\n key1=int,... - each column key with the corresponding data type(int or txt) (Syntax: keyname=type)",
    description="This command creates a new table in the database.",
    usage="name <primary_key> key1=int key2=txt ...",
    aliases=["table"]
  )
  @has_admin_role()
  async def _createtable(self, context, _name, _primary_keys, *args):
    tmp = tuple([v.split("=") for v in args])
    kwargs = {v[0]:v[1] for v in tmp}
    self.bot.db[context.guild.id].create_table(_name, _primary_keys, **kwargs)
    await context.send(self.bot.db[context.guild.id].info(_name))
    fields = {
      "Table":_name,
      "Primary Keys":", ".join(_primary_keys.split(",")),
      "Columns":", ".join([f"{arg[0]}:{arg[1]}" for arg in tmp])
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="created table",
      fields=fields, timestamp=context.message.created_at
    )

  @_db.command(
    name="insert",
    brief="Inserts or updates a row.",
    help="Parameters:\n  name - the name of the table\n  primary_key - the value of the primary key\n  value1 value2 ... - the values of each column in the order as specified in the command: `{prefix}db info tablename`",
    description="This command inserts or updates a row with the primary_key.",
    usage="name primary_key value1 value2 ...",
    aliases=["update", "set"]
  )
  @has_admin_role()
  async def _insert_or_replace(self, context, _name, *args):
    combined_key = self.bot.db[context.guild.id].insert_or_update(_name, *args)
    await context.send(f"Updated entry {combined_key} in table {_name}.")
    fields = {
      "Table":_name,
      "Entry":combined_key
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="updated entry",
      fields=fields, timestamp=context.message.created_at
    )

  @_db.group(
    name="delete",
    brief="Deletes table or row",
    usage="<command>",
    invoke_without_command=True,
    aliases=["drop", "del", "rm"]
  )
  @has_admin_role()
  async def _db_delete(self, context):
    await context.send_help("db delete")

  @_db_delete.command(
    name="row",
    brief="Deletes a row.",
    help="Parameters:\n  name - the name of the table\n  value1 value2 ... - the values of the primary keys",
    description="This command deletes a row.",
    usage="name value1 value2 ...",
  )
  @has_admin_role()
  async def _db_delete_row(self, context, _name, *args):
    self.bot.db[context.guild.id].delete_row(_name, args)
    _key = " ".join(args)
    await context.send(f"Deleted row {_key} in table {_name}.")
    fields = {
      "Table":_name,
      "Entry":_key
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="deleted entry",
      fields=fields, timestamp=context.message.created_at
    )

  @_db_delete.command(
    name="table",
    brief="Deletes a table",
    help="Parameters:\n  name - the name of the table",
    description="This command deletes a table from the database.",
  )
  @has_admin_role()
  async def _db_drop_table(self, context, _name):
    self.bot.db[context.guild.id].delete_table(_name)
    await context.send(f"Deleted table {_name}.")
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="deleted table",
      description=f"**Table:**\n{_name}", timestamp=context.message.created_at
    )


  @_db.command(
    name="select",
    brief="Gets entry from table",
    help="Parameters:\n name - the name of the table\n value - the value of the primary key",
    description="This command fetches one entry from a table with a given primary key, or all if none is given.",
    usage="tablename [value]",
    aliases=["fetch","get"]
  )
  @has_admin_role()
  async def _select_by_key(self, context, _name, *_values):
    if len(_values) == 0:
      results = self.bot.db[context.guild.id].select(_name)
      if results:
        i=0
        for result in results:
          result_string = "\n".join([f"{k} = {v}" for k,v in result.items()])
          #log_entry = ", ".join([f"{k}={v}" for k,v in result.items()])
          await context.send(f"Result {i}:\n```{result_string}```")
          i+=1
      else:
        await context.send(f"Result:\n```No entry```")
      fields = {
        "Table":_name,
        "Result":f"{len(results) if results else 0} entries"
      }
      await self.bot.log_message(context.guild, "ADMIN_LOG",
        user=context.author, action="selected table",
        fields=fields, timestamp=context.message.created_at
      )

    else:
      result = self.bot.db[context.guild.id].select(_name, _values)
      if result:
        result_string = "\n".join([f"{k} = {v}" for k,v in result.items()])
        await context.send(f"Result:\n```{result_string}```")
        # truncate the result for logging
      else:
        await context.send(f"Result:\n```No entry```")
      result = str(result)
      fields = {
                "Table":_name,
                "Key":_values,
                "Result":result[:1021] + '...' if len(result) > 1021 else result
      }
      await self.bot.log_message(context.guild, "ADMIN_LOG",
        user=context.author, action="selected entry",
        fields=fields, timestamp=context.message.created_at
      )

  @_db.command(
    name="query",
    brief="Executes a query",
    help="Parameters:\n  query - the query to execute",
    description="This command executes the query string. WARNING: There are no sanity checks and this method is vulnerable to an injection attack."
  )
  @commands.is_owner()
  async def _execute_query(self, context, *, query):
    result = self.bot.db[context.guild.id].query(query)
    if result is None:
      await context.send("Query executed.")
    else:
      await context.send(f"Query result:```{result}```")
    result = str(result) if result else None
    fields = {
      "Query":query,
      "Result":result[:1021] + '...' if result and len(result) > 1021 else result
    }
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="executed query",
      fields=fields, timestamp=context.message.created_at
    )


  @_db.command(
    name="info",
    brief="Displays info on the db",
    help="Parameters:\n  name - the name of the table",
    description="This command displays info on the database or a given table.",
  )
  @has_admin_role()
  async def _info(self, context, _name=None):
    await context.send(self.bot.db[context.guild.id].info(_name))
    
  @_db.command(
    name="backup",
    brief="Backs up database",
  )
  @commands.max_concurrency(1)
  @commands.is_owner()
  async def _backup(self, context):
    try:
      await context.send(f"```Backing up the database...```")
      backupFolder = f"backup_{round(time.time())}"
      os.mkdir(backupFolder)
      for files in os.listdir(path):
        if files.endswith('.json') or files.endswith('.db'):
          shutil.copyfile(os.path.join(path, files), os.path.join(backupFolder,files))
      await context.send(f"```Completed```")
    except Exception as e:
      raise e
    await self.bot.log_message(context.guild, "ADMIN_LOG",
      user=context.author, action="backed up database",
      timestamp=context.message.created_at
    )

  @_backup.error
  async def _backup_error(self, context, error):
    if isinstance(error, commands.CheckFailure):
      await context.send(f"Sorry {context.author.mention}, but you do not have permission to backup data.")
    elif isinstance(error, commands.MaxConcurrencyReached):
      await context.send(f"Sorry {context.author.mention}, but only {error.number} user(s) can execute `{context.command.qualified_name}` at the same time!")
    else:
      await context.send(f"Sorry {context.author.mention}, something unexpected happened while backing up data.")

#This function is needed for the load_extension routine.
def setup(bot):
  bot.add_cog(DatabaseManagementCog(bot))
  print("Added database management.")
