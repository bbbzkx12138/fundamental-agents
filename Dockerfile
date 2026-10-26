FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY fundamental_agent ./fundamental_agent
RUN python -m pip install --upgrade pip && python -m pip install .

COPY data/cache ./data/cache

EXPOSE 8000

CMD ["uvicorn", "fundamental_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
