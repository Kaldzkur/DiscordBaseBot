try:
  from pysqlite3 import dbapi2 as sqlite3
except:
  import sqlite3
import re
import os
from base.modules.constants import DB_PATH as path

class DatabaseManager:
  allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
  DBType = {
    "int" : "integer",
    "int_not_null":"integer NOT NULL",
    "txt" : "text",
    "txt_not_null":"text NOT NULL",
    "num" : "numeric",
    "num_not_null":"numeric NOT NULL",
    "real": "real",
    "real_not_null":"real NOT NULL",
    "blob": "blob",
    "blob_not_null":"blob NOT NULL",
  }
  
  #Manages a connection to a single database.
  def __init__(self, _name):
    self.name = _name
    self.open()

  def open(self):
    self.connection = sqlite3.connect(self.name)

  def check_name(self, _name):
    if not _name[0].isalpha():
      raise NameError(f"the name {_name} must start with a letter; digits are not allowed.")
    for c in _name:
      if c not in self.allowed_chars:
        raise NameError(f"the name {_name} has forbidden characters; only a-zA-Z0-9 and _ are allowed.")

  def create_table(self, _name, _primary_keys, **kwargs):
    self.check_name(_name)
    for k in _primary_keys:
      if k not in kwargs:
        raise KeyError(f"there must be a column for PRIMARY KEY {k}.")
      self.check_name(k)
    for k in kwargs.keys():
      self.check_name(k)
    values = ",".join([f"{k} {self.DBType[v] if v in self.DBType else v}" for k,v in kwargs.items()])
    primary_keys = ",".join([k for k in _primary_keys])
    try:
      with self.connection as conn:
        #print(f'CREATE TABLE IF NOT EXISTS {_name} ({values}, PRIMARY KEY({primary_keys}))')
        conn.execute(f'CREATE TABLE IF NOT EXISTS {_name} ({values}, PRIMARY KEY({primary_keys}))')
    except Exception:
      raise RuntimeError("the execution of `CREATE TABLE` failed.")

  def insert_or_update(self, _name, _primary_keys, **kwargs):
    self.check_name(_name)
    p_string = ",".join(["?" for i in range(len(kwargs))])
    t_string = ",".join([k for k,v in kwargs.items()])
    values_in = tuple([v for k,v in kwargs.items()])
    update = ",".join([f"{k}=excluded.{k}" for k,v in kwargs.items() if k not in _primary_keys])
    try:
      with self.connection as conn:
        conn.execute(f'INSERT INTO {_name}({t_string}) VALUES ({p_string}) ON CONFLICT({",".join(_primary_keys)}) DO UPDATE SET {update}', values_in)
    except Exception:
      raise RuntimeError("the execution of `INSERT INTO` failed.")

  def delete_table(self, _name):
    self.check_name(_name)
    try:
      with self.connection as conn:
        conn.execute(f"DROP TABLE IF EXISTS {_name}")
    except Exception:
      raise RuntimeError("the execution of `DROP TABLE` failed.")

  def delete_row(self, _name, _primary_keys, _values):
    if len(_primary_keys) != len(_values):
      if len(_primary_keys) > len(_values):
        raise KeyError("I'm missing some values for the primary keys.")
      elif len(_primary_keys) < len(_values):
        raise KeyError("I'm missing some keys for the passed values.")
    self.check_name(_name)
    for k in _primary_keys:
      self.check_name(k)
    condition = " AND ".join([f'{k}="{v}"' for k,v in zip(_primary_keys, _values)])
    try:
      with self.connection as conn:
        conn.execute(f"DELETE FROM {_name} WHERE {condition}")
    except Exception as e:
      raise RuntimeError("the execution of `SELECT ALL` failed.")

  def select_one(self, _name, _primary_keys, _values):
    if len(_primary_keys) != len(_values):
      if len(_primary_keys) > len(_values):
        raise KeyError("I'm missing some values for the primary keys.")
      elif len(_primary_keys) < len(_values):
        raise KeyError("I'm missing some keys for the passed values.")
    for k in _primary_keys:
      self.check_name(k)
    condition = " AND ".join([f'{k}="{v}"' for k,v in zip(_primary_keys, _values)])
    try:
      with self.connection as conn:
        #print(f"Select * FROM {_name} WHERE {condition}")
        return conn.execute(f"Select * FROM {_name} WHERE {condition}").fetchone()
    except Exception:
      raise RuntimeError("the execution of `SELECT ONE` failed.")

  def select_all(self, _name):
    self.check_name(_name)
    try:
      with self.connection as conn:
        return conn.execute(f"Select * FROM {_name}").fetchall()
    except Exception as e:
      raise RuntimeError("the execution of `SELECT ALL` failed.")

  def query(self, query):
    try:
      with self.connection as conn:
        result = conn.execute(query)
        if re.search("(SELECT|Select|select)", query):
          return result.fetchall()
    except Exception:
      raise RuntimeError("the execution of the query failed.")

  def info(self, _table=None):
    if _table is None:
      try:
        with self.connection as conn:
          return conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
      except Exception:
        raise RuntimeError(f"could not get info on database.")
    else:
      try:
        with self.connection as conn:
          return conn.execute(f"PRAGMA table_info('{_table}')").fetchall()
      except Exception:
        raise RuntimeError(f"could not get info to table {_table}.")
  def close(self):
    self.connection.close()

class Database(DatabaseManager):
  def __init__(self, _identifier):
    if not os.path.isdir(path):
      os.mkdir(path)
    super().__init__(f"{path}/data_{_identifier}.db")
    self.id = _identifier
    self.tables = {}
    try:
      self._import()
    except:
      pass

  def __contains__(self, _name):
    return _name in self.tables

  def _import(self):
    tables = super().info()
    for table in tables:
      columns = super().info(table[0])
      primary_keys = ([col[1] for col in columns if col[5] > 0])
      self.tables[table[0]] = {
        "primary_key":primary_keys,
        "columns":{col[1]:col[2] for col in columns}
      }

  def create_table(self, _name, _primary_keys, **kwargs):
    if type(_primary_keys) == str:
        _primary_keys = _primary_keys.split(",")
    elif type(_primary_keys) not in [list, tuple]:
        raise KeyError("PRIMARY KEYs must be of type str, list or tuple: {type(_primary_keys)}")
    super().create_table(_name, _primary_keys, **kwargs)
    self.tables[_name] = {
      "primary_key":_primary_keys,
      "columns":kwargs
    }

  def insert_or_update(self, _name, *args):
    try:
      kwargs = {k:v for k,v in zip(self.tables[_name]["columns"].keys(), args)}
    except KeyError:
      raise LookupError(f" the table {_name} does not exist.")
    expected_len = len(self.tables[_name]['columns'].keys())
    actual_len = len(args)
    if expected_len != actual_len:
      raise IndexError(f"I expected {expected_len} values in insert, but got {actual_len}.")
    #Check if type matches the table
    for (k,t),v in zip(self.tables[_name]["columns"].items(), args):
      if v is None:
        continue # do not check None type
      if "int" in t:
        try:
          int(v)
        except ValueError:
          raise TypeError(f"wrong type for column {k}: must be int")
      elif "real" in t:
        try:
          float(v)
        except ValueError:
          raise TypeError(f"wrong type for column {k}: must be float")
      elif "txt" in t:
        try:
          str(v)
        except ValueError:
          raise TypeError(f"wrong type for column {k}: must be str")
    super().insert_or_update(_name, self.tables[_name]["primary_key"], **kwargs)
    pkeys = self.tables[_name]["primary_key"]
    cols = self.tables[_name]["columns"].keys()
    return " ".join([str(a) for c,a in zip(cols, args) if c in pkeys])

  def delete_table(self, _name):
    super().delete_table(_name)
    if _name in self.tables:
      del self.tables[_name]

  def delete_row(self, _name, _values=None):
    expected_len = len(self.tables[_name]["primary_key"])
    if _values is not None:
      if type(_values) in [str, int, float]:
        _values = (_values,)
      elif type(_values) not in [list, tuple]:
        raise ValueError("values must be of type str, int, float, list or tuple.")
      actual_len = len(_values)
      if expected_len != actual_len:
        raise IndexError(f"Expected {expected_len} values in delete_row, but got {actual_len}.")
      result = super().delete_row(_name, self.tables[_name]["primary_key"], _values)
    else:
      raise ValueError(f"Expected {expected_len} values in delete_row, but got 0.")

  def select(self, _name, _values=None):
    if _values is not None:
      if type(_values) in [str, int, float]:
        _values = (_values,)
      elif type(_values) not in [list, tuple]:
        raise ValueError("values must be of type str, int, float, list or tuple.")
      expected_len = len(self.tables[_name]["primary_key"])
      actual_len = len(_values)
      if expected_len != actual_len:
        raise IndexError(f"Expected {expected_len} values in select, but got {actual_len}.")
      result = super().select_one(_name, self.tables[_name]["primary_key"], _values)
      if result is not None:
        return {k:v for k,v in zip(self.tables[_name]["columns"], result)}
    else:
      result = super().select_all(_name)
      if len(result) > 0:
        tmp = []
        for row in result:
          tmp.append({k:v for k,v in zip(self.tables[_name]["columns"], row)})
        return tmp

  def close(self):
    super().close()

  def info(self, _name=None):
    if _name is None:
      tables = super().info()
      table_names = ", ".join([k[0] for k in tables])
      return (f"Database: {self.name}\n"
              f"```Tables: {len(tables)}\n{table_names}```")
    else:
      columns = super().info(_name)
      if columns is None:
        raise LookupError(f"the table {_name} does not exist.")
      column_str = "\n  ".join([f"{col[1]}{'(primary)' if col[5] > 0 else ''}: {self.DBType[col[2]] if col[2] in self.DBType else col[2]}" for col in columns])
      return (f"Table: {_name}\n"
              f"```Columns:\n  {column_str}```")

if __name__ == "__main__":
  db = Database("stats", [])
  db.create_table("hero", "name", name="txt_not_null", hp="int")
  db.insert_or_update("hero", "leif", 1000)
  db.insert_or_update("hero", "fee", 500)
  print(db.info())
  print(db.info("hero"))
