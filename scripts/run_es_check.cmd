@echo off
cd /d "%~dp0.."
python scripts\check_es_health.py > _es_health_result.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL%>> _es_health_result.txt
type _es_health_result.txt
