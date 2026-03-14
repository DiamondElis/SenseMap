# Airflow image with PDF ingestion + entity/relation extraction deps
FROM apache/airflow:2.10.0
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m spacy download en_core_web_sm
USER airflow
