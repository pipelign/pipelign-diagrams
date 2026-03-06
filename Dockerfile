FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jdk-headless libharfbuzz0b libfreetype6 fontconfig && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/plantuml
COPY deps/plantuml/plantuml*.jar /app/plantuml/plantuml.jar

ENV PLANTUML_JAR_PATH=/app/plantuml/plantuml.jar

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

