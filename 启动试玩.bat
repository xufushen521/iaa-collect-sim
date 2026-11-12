@echo off
chcp 65001 >nul
cd /d "%~dp0"
title IAA 七格收集三消
python -m streamlit run app.py
pause
