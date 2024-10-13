@echo off
:restart
git fetch
git pull
python main.py
if ERRORLEVEL 1 goto restart
