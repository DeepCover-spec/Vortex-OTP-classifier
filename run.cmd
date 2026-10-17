@echo off
rem Windows cmd equivalent of the Makefile. Usage: run.cmd train
if "%1"=="data" goto data
if "%1"=="train" goto train
if "%1"=="eval" goto eval
if "%1"=="up" goto up
if "%1"=="demo" goto demo
if "%1"=="retrain" goto retrain
echo Usage: run.cmd data^|train^|eval^|up^|demo^|retrain
goto :eof
:data
py data\generate.py
goto :eof
:train
py src\train.py
goto :eof
:eval
py src\evaluate.py
goto :eof
:up
docker compose up --build
goto :eof
:demo
py scripts\run_shift_demo.py
goto :eof
:retrain
py src\retrain.py
goto :eof