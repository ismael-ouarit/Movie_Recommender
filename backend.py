import os
import re

from flask import Flask, request, jsonify
from elasticsearch import Elasticsearch
import requests
from recommender import get_recommendations, get_generic_recommendations

app = Flask(__name__)

# Connect to Elasticsearch (credentials supplied via environment variables)
ES_URL = os.environ["ELASTICSEARCH_URL"]
ES_API_KEY = os.environ["ELASTICSEARCH_API_KEY"]
es = Elasticsearch(ES_URL, api_key=ES_API_KEY)

INDEX_NAME = "movies"

# TMDb API configuration
TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

def get_tmdb_metadata(title):
    """
    Fetch movie poster URL and language from TMDb API.
    Cleans alternative titles (a.k.a.) and parses the year to ensure a high-accuracy hit.
    Returns (poster_url, language) or (None, "") if not found.
    """
    # 1. Extract the release year matching (YYYY) at the end of the string
    year_match = re.search(r'\((\d{4})\)\s*$', title)
    year = year_match.group(1) if year_match else None
    
    # 2. Strip out any "(a.k.a. Everything Else)" formatting
    clean_title = re.sub(r'\(a\.k\.a\.[^)]+\)', '', title)
    
    # 3. Strip out the trailing year (YYYY)
    clean_title = re.sub(r'\(\d{4}\)\s*$', '', clean_title).strip()
    
    params = {
        "api_key": TMDB_API_KEY,
        "query": clean_title,
    }
    if year:
        params["primary_release_year"] = year

    try:
        resp = requests.get(TMDB_SEARCH_URL, params=params, timeout=5)
        data = resp.json()
        if data.get("results"):
            first = data["results"][0]
            poster_path = first.get("poster_path")
            poster = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
            return poster, first.get("original_language", "")
    except Exception:
        pass
    return None, ""

@app.route("/api/autocomplete", methods=["GET"])
def autocomplete():
    #Gets "query" parameter from URL
    query = request.args.get("query", "")

    #If user sends empty string, return nothing
    if not query:
        return jsonify([])
    
    #Searches through Elasticsearch "movies" index
    response = es.search(
        index = "movies",
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "type": "bool_prefix",
                    "fields": [
                        "title",
                        "title._2gram",
                        "title._3gram"
                    ]
                }
            },
            "size": 10
        }
    )

    #Extracts the data from the response and builds a list
    results = []
    for hit in response["hits"]["hits"]:
        results.append({
            "movieID": hit["_source"]["movieID"],
            "title": hit["_source"]["title"],
            "genres": hit["_source"]["genres"]
        })

    #Returns the results as a JSON file
    return jsonify(results)


@app.route("/api/poster", methods=["GET"])
def poster():
    """
    Returns the TMDb poster URL and original language for a given movie title.
    """
    title = request.args.get("title", "")
    if not title:
        return jsonify({"poster": None, "language": "Unknown"})
    poster_url, language = get_tmdb_metadata(title)
    return jsonify({"poster": poster_url, "language": language or "Unknown"})


@app.route("/api/recommendations", methods=["POST"])
def recommendations():
    """
    Accepts JSON: { "movie_ids": [1, 3, 5, 7] }
    - If movie_ids is empty: returns generic popular movies.
    - If movie_ids has values: returns personalized recommendations.
    Each result is enriched with a poster URL from TMDb.
    """
    data = request.get_json(silent=True) or {}
    movie_ids = data.get("movie_ids", [])

    try:
        # Choose personalized or generic recommendations
        if movie_ids:
            df = get_recommendations(movie_ids)
        else:
            df = get_generic_recommendations()

        # Build the response list and attach poster URLs
        results = []
        for _, row in df.iterrows():
            poster_url, lang = get_tmdb_metadata(row["title"])
            results.append({
                "movieID": int(row["movieId"]),
                "title": row["title"],
                "genres": row["genres"],
                "language": row.get("language") or lang,
                "avg_score": float(f"{float(row['avg_score']):.3f}"),
                "recommended_by": int(row["recommended_by"]),
                "poster": poster_url
            })

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
