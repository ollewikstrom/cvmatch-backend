.\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level trace --access-log
