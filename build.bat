@echo off
rem ============================================
rem  打包桌宠 exe（onedir：解压即用，启动快）
rem  产物: release\兔团子桌宠\兔团子桌宠.exe
rem  发给对方前请先清空该目录下 config\config.yaml
rem  里的 api_key / sessdata（不带走你的凭据）
rem ============================================
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [ERROR] 未安装 PyInstaller，请先运行:
    echo     .venv\Scripts\pip install pyinstaller
    pause
    exit /b 1
)

".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name "兔团子桌宠" ^
    --distpath release --workpath build-tmp ^
    --collect-all PySide6 ^
    main.py

if errorlevel 1 (
    echo [ERROR] 打包失败，请查看上方报错
    pause
    exit /b 1
)

rem 清理中间产物
rmdir /s /q build-tmp 2>nul
del /q "兔团子桌宠.spec" 2>nul

echo.
echo [完成] 打包成功: release\兔团子桌宠\兔团子桌宠.exe
echo       将整个 "兔团子桌宠" 文件夹压缩发给对方即可
echo       对方双击 exe，首次会自动弹出设置面板
pause
