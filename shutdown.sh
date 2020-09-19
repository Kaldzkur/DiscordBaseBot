#!/bin/sh
#kill all python3 processes
sudo pkill -9 python3
#wait for all processes to end
PID=$(/usr/bin/pgrep python3)
while [ "$PID" != "" ];do
  sleep 1
  sudo pkill -9 python3
  PID=$(/usr/bin/pgrep python3)
done
