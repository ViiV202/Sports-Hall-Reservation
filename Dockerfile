FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py migrations.py rate_limiter.py db.py bot_instance.py keyboards.py bot.py ./
COPY handlers/ ./handlers/

RUN chown -R appuser:appgroup /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import db, sys; sys.exit(0 if db.health_check() else 1)"

CMD ["python", "bot.py"]
