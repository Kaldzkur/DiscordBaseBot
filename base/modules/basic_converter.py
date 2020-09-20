from discord.ext import commands
from dateutil import parser, tz
from datetime import datetime, timedelta
import pytz
import re
from emoji import UNICODE_EMOJI


def FutureTimeConverter(argument):
  try: # parse it as a deltatime object
    return datetime.now(pytz.utc) + TimedeltaConverter(argument)
  except: # parse it as a datetime object
    return DateConverter(argument)
    
def PastTimeConverter(argument):
  try: # parse it as a deltatime object
    return datetime.now(pytz.utc) - TimedeltaConverter(argument)
  except: # parse it as a datetime object
    return DateConverter(argument)
    
def DateConverter(argument):
  date = parser.parse(argument)
  if date.tzinfo is None: # if no timezone tag, process it as UTC time
    date = pytz.utc.localize(date)
  return date
  
def TimedeltaConverter(argument):
  regex = re.compile(r'((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')
  parts = regex.match(argument)
  if not parts:
    raise Exception # cannot parse
  parts = parts.groupdict()
  time_params = {}
  for (name, param) in parts.items():
    if param:
      time_params[name] = int(param)
  if not time_params:
    raise Exception # cannot parse
  return timedelta(**time_params)
    

class EmojiUnion(commands.EmojiConverter):
  # return a str if the argument is a unicode emoji, or an emoji if the argument is a custom emoji
  async def convert(self, ctx, argument):
    if argument in UNICODE_EMOJI:
      return argument
    return await super().convert(ctx, argument)
    
  
def parse_arguments(argument, separator):
  attributes = {}
  while len(argument) > 0:
    try:
      line, argument = argument.split(separator, 1)
    except:
      line = argument
      argument = ""
    try:
      attribute, value = line.split("=", 1)
      attribute = attribute.strip().lower()
      if len(attribute) == 0:
        raise commands.UserInputError("Unexpected format, cannot read attributes")
      if attribute == "cmd_text":
        argument = value + "\n" + argument
        break
      attributes[attribute] = value
    except:
      # not a name-value pair, this means the remaining is cmd_text
      argument = line + "\n" + argument
      break
  return (attributes, argument.strip())
      
      
def tobool(arg):
  if arg.lower() in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
    return True
  elif arg.lower() in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
    return False
  raise commands.UserInputError("Unexpected format for bool arguments")
  
def tolist(arg):
  return list(filter(None, arg.split()))
  
def filter_attributes(attributes, string_attributes=None, bool_attributes=None, list_attributes=None):
  if string_attributes is None:
    string_attributes = []
  if bool_attributes is None:
    bool_attributes = []
  if list_attributes is None:
    list_attributes = []
  filtered_attri = {}
  for k, v in attributes.items():
    if k in string_attributes:
      filtered_attri[k] = v
    elif k in bool_attributes:
      filtered_attri[k] = tobool(v)
    elif k in list_attributes:
      filtered_attri[k] = tolist(v)
  return filtered_attri
  
def cmd_arg_converter(argument):
  attributes, cmd_text = parse_arguments(argument, '\n')
  string_attributes = ["help", "brief", "usage", "description"]
  bool_attributes = ["enabled", "hidden", "ignore_extra", "cooldown_after_parsing", "invoke_without_command", "case_insensitive"]
  list_attributes = ["aliases"]
  return (filter_attributes(attributes, string_attributes, bool_attributes, list_attributes), cmd_text)
  
def cmd_name_converter(argument):
  return " ".join(argument.split())
