FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --create-home backend
USER backend
CMD ["uvicorn","marketing_backend.api:app","--host","0.0.0.0","--port","8000"]
