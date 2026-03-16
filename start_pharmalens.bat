@echo off

echo Starting PharmaLens AI Server...

cd /d C:\Users\AHMED\Desktop\pharmalens-ai

call venv\Scripts\activate

start http://127.0.0.1:8000

uvicorn main:app --reload