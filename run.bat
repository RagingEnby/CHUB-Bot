@echo off
:restart
python main.py
if ERRORLEVEL 1 goto restart