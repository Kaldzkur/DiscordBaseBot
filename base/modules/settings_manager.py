import inspect
from base.modules.db_manager import Database

class DefaultSetting:
  # a class to store a default setting
  # transFun is a function to transform the value of a setting from string to something else
  # checkFun is a function to check the validity of a setting, it must return a boolean
  # adaptFun is a function to adapt the setting to the new value in the bot, it takes two arguments: value and context
  def __init__(self, name, default, description="", transFun=None, checkFun=None, checkDescription="", adaptFun=None):
    self.name = name
    self.description = description
    self.transFun = transFun
    self.checkFun = checkFun
    self.checkDescription = checkDescription
    self.adaptFun = adaptFun
    if transFun is not None:
      self.default = transFun(default)
    else:
      self.default = default
    assert self.default is not None
    if checkFun is not None:
      assert checkFun(default)
    if adaptFun is not None:
      assert inspect.isfunction(adaptFun)
      
  def transform_setting(self, value):
    if self.transFun is not None:
      value = self.transFun(value)
    return value
    
  async def adapt_setting(self, value, context, oldvalue=None):
    try:
      # transform the value
      value = self.transform_setting(value)
      # check the value is valid or not
      if self.checkFun is not None:
        assert self.checkFun(value)
      if value == oldvalue:
        return value
    except:
      if self.checkDescription:
        raise TypeError(f"setting {self.name} has to be {self.checkDescription}.")
      else:
        raise TypeError(f"setting {self.name} does not have the expected format.")
    # adapt the setting in the bot
    if self.adaptFun is not None:
      if inspect.iscoroutinefunction(self.adaptFun):
        await self.adaptFun(value, context)
      else:
        self.adaptFun(value, context)
    return value


class Settings:

  def __init__(self, database, **kwargs):
    self.db = database
    self.id = self.db.id
    self.db.create_table("bot_settings", "name", name="txt", value="txt", description="txt")
    
    # load the db content to memory
    self.load_memory()
    for key, value in kwargs.items():
      if key in self.memory:
        self.set(key, value)

  def __contains__(self, key):
    return key in self.memory
    
  def load_memory(self):
    self.memory = {}
    result = self.db.select("bot_settings")
    if result is not None:
      for row in result:
        self.memory[row["name"]] = [row["value"], row["description"]]

  def get(self, key):
    if key not in self.memory:
      raise LookupError(f"{key} does not exist.")
    return self.memory[key][0]

  def set(self, key, value):
    if key not in self.memory:
      raise LookupError(f"{key} does not exist.")
    self.db.insert_or_update("bot_settings", key, value, self.memory[key][1])
    self.memory[key][0] = value

  def add(self, key, value):
    if key in self.memory:
      raise LookupError(f"{key} already exists.")
    self.db.insert_or_update("bot_settings", key, value, "no description")
    self.memory[key] = [value, "no description"]

  def add_description(self, key, value):
    if key not in self.memory:
      raise LookupError(f"{key} does not exists.")
    self.db.insert_or_update("bot_settings", key, self.memory[key][0], value)
    self.memory[key][1] = value

  def rm(self, key):
    if key not in self.memory:
      raise LookupError(f"t{key} does not exist.")
    self.db.delete_row("bot_settings", key)
    self.memory.pop(key, None)

  def info(self):
    max_len = max([len(k) for k in self.memory])+2
    setting_str = "\n".join([f"{k+':':<{max_len}}{v[1]}" for k,v in self.memory.items()])
    return f"Possible Settings:\n{setting_str}"
