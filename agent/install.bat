@echo off
REM OpenClaw Watch Agent 安装脚本 (Windows)

echo ========================================
echo OpenClaw Watch Agent 安装脚本 (Windows)
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 需要安装 Python 3
    pause
    exit /b 1
)

REM 获取 NAS 地址
set /p NAS_URL="请输入 NAS 服务地址 (例如 http://192.168.1.100:9000): "

REM 获取 API Key
set /p API_KEY="请输入设备 API Key: "

if "%API_KEY%"=="" (
    echo 错误: API Key 不能为空
    pause
    exit /b 1
)

REM 安装依赖
echo 安装依赖...
pip install -q requests psutil

REM 创建配置
echo # OpenClaw Watch Agent 配置 > openclaw_watch.env
echo NAS_URL=%NAS_URL% >> openclaw_watch.env
echo API_KEY=%API_KEY% >> openclaw_watch.env
echo REPORT_INTERVAL=30 >> openclaw_watch.env

echo 配置文件已创建: openclaw_watch.env

REM 创建启动脚本
echo @echo off > start_agent.bat
echo setlocal >> start_agent.bat
echo for /f "tokens=*" %%a in (openclaw_watch.env) do set %%a >> start_agent.bat
echo endlocal ^& set NAS_URL=%%NAS_URL%% ^& set API_KEY=%%API_KEY%% >> start_agent.bat
echo python agent.py %%* >> start_agent.bat

echo.
echo ========================================
echo 安装完成!
echo ========================================
echo.
echo 启动 Agent: start_agent.bat
echo.
pause
