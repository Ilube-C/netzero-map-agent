# Backend + static frontend. Built from the repo root: main.py resolves the
# frontend at parents[2]/"frontend", so the /app/backend/app + /app/frontend
# layout below must be preserved.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app ./backend/app
COPY frontend ./frontend

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000"]
