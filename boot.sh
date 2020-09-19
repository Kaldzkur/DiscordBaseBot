#!/bin/sh
mkdir -p log
python3 -u base_bot.py >> ./log/`date +%s`.txt
