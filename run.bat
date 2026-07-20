@echo off
echo تركيب المكتبات المطلوبة...
pip install -r requirements.txt
echo.
echo تشغيل الموقع...
echo افتح المتصفح على: http://localhost:5000
python app.py
pause
