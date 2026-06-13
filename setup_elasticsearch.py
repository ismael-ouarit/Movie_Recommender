import csv
import os
from elasticsearch import Elasticsearch, helpers

# 1. Connect to Elastic Serverless (credentials supplied via environment variables)
es = Elasticsearch(
    os.environ["ELASTICSEARCH_URL"],
    api_key=os.environ["ELASTICSEARCH_API_KEY"]
)

INDEX_NAME = "movies"

def create_index():
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)

    # Configure "search_as_you_type" for fast autocomplete
    mapping = {
        "mappings": {
            "properties": {
                "movieID": {"type": "keyword"},
                "title": {"type": "search_as_you_type"},
                "genres": {"type": "keyword"}
            }
        }
    }
    es.indices.create(index=INDEX_NAME, body=mapping)
    print(f"Created index: {INDEX_NAME}")

def ingest_data(csv_path="ml-small-movies.csv"):
    actions = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {
                "_index": INDEX_NAME,
                "_id": row["movieId"],
                "_source": {
                    "movieID": row["movieId"],
                    "title": row["title"],
                    "genres": row["genres"].split("|")
                }
            }
            actions.append(doc)

    # Bulk insert for maximum speed
    helpers.bulk(es, actions)
    print(f"Successfully ingested {len(actions)} movies into Elasticsearch!")

if __name__ == "__main__":
    create_index()
    ingest_data("ml-small-movies.csv")
