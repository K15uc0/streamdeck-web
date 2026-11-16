@echo off
cd /d "%~dp0"
title Stream Deck
python server.py
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar. O Python esta instalado? Baixe em python.org e marque "Add python.exe to PATH".
)
pause
