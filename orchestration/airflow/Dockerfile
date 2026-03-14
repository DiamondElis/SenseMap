# Airflow image with PDF ingestion pipeline deps (neo4j, openai, pypdf)
FROM apache/airflow:2.10.0
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
USER airflow
