#!/bin/sh
mkdir -p log
output=./log/`date +%s`.txt
python3 -u base_bot.py > $output 2>&1
