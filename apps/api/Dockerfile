FROM python:3.12-slim

WORKDIR /app

COPY apps/api/requirements.txt ./requirements.txt
# --timeout/--retries: устойчивость к медленным сетям (прокси кампуса)
RUN pip install --no-cache-dir --timeout 180 --retries 10 -r requirements.txt

COPY apps/api/app ./app
COPY apps/api/tests ./tests

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
