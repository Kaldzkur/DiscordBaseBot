#!/bin/sh
PID=$(/usr/bin/pgrep -f base_bot.py)
if [ "$PID" != "" ]
then
  echo "Bot is already running"
else
  mkdir -p log
  output=./log/`date +%s`.txt
  #We redirect stdout to output and then redirect stderr to stdout
  nohup python3 -u base_bot.py > output 2>&1 &
fi
