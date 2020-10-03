import asyncio
import discord
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
  
class Timer:
  def __init__(self, timeout, callback, *args, **kwargs):
    self._timeout = timeout
    self._callback = callback
    self.args = args
    self.kwargs = kwargs
    self._task = asyncio.ensure_future(self._job())

  async def _job(self):
    await asyncio.sleep(self._timeout)
    await self._callback(*self.args, **self.kwargs)

  def cancel(self):
    self._task.cancel()
    
class BotTimer(Timer):
  def __init__(self, bot, guild, task, timeout, callback, *args, **kwargs):
    self.bot = bot
    self.guild = guild
    self.task = task
    super().__init__(timeout, callback, *args, **kwargs)
    logger.debug(f"Set up scheduled task '{self.task}' in {timeout}s.")

  async def _job(self):
    try:
      await asyncio.sleep(self._timeout)
      logger.debug(f"Run scheduled task: {self.task}.")
      await self._callback(*self.args, **self.kwargs)
      logger.debug(f"Finished scheduled task: {self.task}.")
    except asyncio.CancelledError:
      pass
    except Exception as error:
      await self.async_timer_error_log(error)
      
  def cancel(self):
    super().cancel()
    logger.debug(f"Cancelled scheduled task {self.task}.")

  async def async_timer_error_log(self, error):
    logger.debug(f"Scheduled task {self.task} received {error.__class__.__name__}: {error}.")
    title = f"A {error.__class__.__name__} occured in Timer"
    fields = {"Method":self._callback.__name__,
              "Task":self.task,
             f"{error.__class__.__name__}":f"{error}"}
    await self.bot.log_message(self.guild, "ERROR_LOG", title=title, fields=fields)

    
def run_bot_coroutine(bot, guild, callback, *args, **kwargs):
  # similar to asyncio.ensure_future but with bot logging
  async def task_with_logging():
    try:
      await callback(*args, **kwargs)
    except Exception as error:
      await bot.on_task_error(f"Coroutine {callback.__name__}", error, guild)
  asyncio.ensure_future(task_with_logging())
  
