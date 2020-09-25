#!/bin/sh
PID=$(/usr/bin/pgrep -f base_bot.py)
if [ "$PID" != "" ]
then
  echo "Bot is already running"
else
  mkdir -p log
  nohup python3 -u base_bot.py >> ./log/`date +%s`.txt &
fi
