# Personal Dashboard

FastAPI + APScheduler + SQLite + static HTML/JS.

## Run
```
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/static/../? Actually root serves static index.html.
