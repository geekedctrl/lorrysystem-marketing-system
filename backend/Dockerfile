FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
ARG INSTALL_DISCOVERY_BROWSER=false
RUN if [ "$INSTALL_DISCOVERY_BROWSER" = "true" ]; then python -m playwright install --with-deps chromium; fi
COPY . .
RUN useradd --create-home backend
USER backend
CMD ["uvicorn","marketing_backend.api:app","--host","0.0.0.0","--port","8000"]
