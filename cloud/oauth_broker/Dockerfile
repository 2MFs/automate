FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.* uvicorn[standard]==0.32.* httpx==0.27.*

COPY main.py /app/main.py

ENV PORT=8080
EXPOSE 8080

# PUBLIC_BASE_URL must be set at runtime, e.g.:
#   docker run -e PUBLIC_BASE_URL=https://broker.example.com \
#              -e OAUTH_GITHUB_CLIENT_ID=...                  \
#              -e OAUTH_GITHUB_CLIENT_SECRET=...              \
#              -p 8080:8080 automate-oauth-broker

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
