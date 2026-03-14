"""
GDS enrichment: project 'kg', then PageRank, Leiden, FastRP, Node Similarity.
Run only after the hybrid graph (entities and relationships) is stable.
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from sensemap.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from sensemap.gds_runner import run_gds_enrichment

SKIP_NODE_SIMILARITY = False  # Set True to run only PageRank, Leiden, FastRP


def task_run_gds(**context):
    run_gds_enrichment(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        skip_node_similarity=SKIP_NODE_SIMILARITY,
    )


with DAG(
    dag_id="gds_enrichment",
    default_args={"owner": "sensemap", "retries": 1},
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    tags=["gds", "enrichment", "pagerank", "leiden", "fastrp"],
) as dag:
    run_gds = PythonOperator(
        task_id="run_gds_enrichment",
        python_callable=task_run_gds,
    )
