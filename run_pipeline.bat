@echo off
REM Get the directory where the batch script is located
set SCRIPT_DIR=%~dp0

REM Activate the virtual environment
echo Activating virtual environment...
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

REM Check if activation was successful (optional, basic check)
if %errorlevel% neq 0 (
    echo Failed to activate virtual environment. Make sure 'venv' exists in %SCRIPT_DIR%
    pause
    exit /b %errorlevel%
)

REM Run the main Python script
echo Running main.py...
python "%SCRIPT_DIR%main.py"

REM Pause at the end to see output (optional)
echo. 
echo Script finished. Press any key to exit.
pause 