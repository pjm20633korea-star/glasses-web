@echo off
chcp 65001 >nul
title 안경원 프로그램 서버 관리
cd /d "%~dp0"

:menu
cls
echo ================================
echo    안경원 프로그램 서버 관리
echo ================================
echo  1. 서버 시작        (접속)
echo  2. 관리자 페이지 열기 (admin)
echo  3. 고객관리 페이지 열기
echo  4. 서버 종료        (접속끊기)
echo  5. 나가기
echo ================================
set /p choice=번호를 입력하고 Enter:

if "%choice%"=="1" goto start_server
if "%choice%"=="2" goto open_admin
if "%choice%"=="3" goto open_main
if "%choice%"=="4" goto stop_server
if "%choice%"=="5" exit
goto menu

:start_server
cls
echo 서버 상태를 확인하는 중...
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel%==0 (
    echo 이미 서버가 실행 중입니다.
) else (
    start "OpticalAppServer" py -3.14 -m uvicorn main:app --port 8000 --reload
    echo 서버를 시작했습니다. 잠시 기다린 뒤 페이지를 열어보세요.
)
echo.
pause
goto menu

:open_admin
start http://localhost:8000/admin
goto menu

:open_main
start http://localhost:8000/
goto menu

:stop_server
cls
set found=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
    set found=1
)
if "%found%"=="1" (
    echo 서버를 종료했습니다.
) else (
    echo 실행 중인 서버가 없습니다.
)
echo.
pause
goto menu
