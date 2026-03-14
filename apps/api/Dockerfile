# Placeholder for FastAPI app — update when app exists
FROM python:3.11-slim

WORKDIR /app
COPY apps/api/ ./
RUN pip install --no-cache-dir fastapi uvicorn

EXPOSE 8000
# Add main.py and use: CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["python", "-m", "http.server", "8000"]
