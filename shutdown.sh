#!/bin/sh
if [ -z "$1" ] ; then
  #No input argument passed -> kill all base_bot instances
  sudo pkill -9 -f base_bot.py
  #wait for all processes to end
  PID=$(/usr/bin/pgrep -f base_bot.py)
  while [ "$PID" != "" ];do
    sleep 1
    sudo pkill -9 -f base_bot.py
    PID=$(/usr/bin/pgrep -f base_bot.py)
  done
else
  #kill only the process with the given pid (arg 1 passed to script)
  sudo kill -9 $1
fi
