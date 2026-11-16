@echo off
rem Construye los .exe de las apps (doble clic, o: construir.bat fsrscope)
cd /d "%~dp0..\.."
python -m pip install -r software\requirements.txt -r software\empaquetado\requirements-build.txt
python software\empaquetado\construir.py %*
pause
