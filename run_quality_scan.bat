@echo off
echo Running Code Quality Scan...

set REPORT_FILE=CI\quality_report.txt
if not exist debug mkdir debug

echo [Quality Scan Report - %DATE% %TIME%] > %REPORT_FILE%
echo =========================================== >> %REPORT_FILE%

echo [1/4] Running isort (Import sorting)...
echo --- ISORT --- >> %REPORT_FILE%
isort . >> %REPORT_FILE% 2>&1

echo [2/4] Running black (Code formatting)...
echo. >> %REPORT_FILE%
echo --- BLACK --- >> %REPORT_FILE%
black . >> %REPORT_FILE% 2>&1

echo [3/4] Running flake8 (Style guide enforcement)...
echo. >> %REPORT_FILE%
echo --- FLAKE8 --- >> %REPORT_FILE%
flake8 . >> %REPORT_FILE% 2>&1

echo [4/4] Running mypy (Static type checking)...
echo. >> %REPORT_FILE%
echo --- MYPY --- >> %REPORT_FILE%
mypy . >> %REPORT_FILE% 2>&1

echo Quality scan complete! Report saved to %REPORT_FILE%
