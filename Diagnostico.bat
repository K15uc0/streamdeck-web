@echo off
cd /d "%~dp0"
title Diagnostico Stream Deck
python diagnostico.py
timeout /t 5
