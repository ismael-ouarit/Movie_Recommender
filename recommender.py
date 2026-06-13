import os

from google.cloud import bigquery

# BigQuery references
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "movie-recommender-492111")
client = bigquery.Client(project=PROJECT)
DATASET = os.getenv("BQ_DATASET", "Movies_Dataset")
MODEL = f"`{PROJECT}.{DATASET}.Movie_Recommender`"
RATINGS_TABLE = f"`{PROJECT}.{DATASET}.Ratings_Lists`"
MOVIES_TABLE = f"`{PROJECT}.{DATASET}.Movie_Table`"


def find_similar_users(selected_movie_ids, top_k=10):
    """
    Step 1: Find users who rated the same movies highly.
    Ranks them by number of shared highly-rated movies.
    """
    query = f"""
    SELECT
      userID,
      COUNT(*) AS num_shared
    FROM {RATINGS_TABLE}
    WHERE movieId IN UNNEST(@movie_ids)
      AND rating_im >= 0.8
    GROUP BY userID
    ORDER BY num_shared DESC
    LIMIT @top_k
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("movie_ids", "INT64", [int(m) for m in selected_movie_ids]),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def get_recommendations(selected_movie_ids, top_k=10, num_recs=20):
    """
    Step 2 & 3: Find similar users, then use ML.RECOMMEND
    to get and aggregate their recommendations.
    """
    query = f"""
    WITH similar_users AS (
      SELECT
        userID,
        COUNT(*) AS num_shared
      FROM {RATINGS_TABLE}
      WHERE movieId IN UNNEST(@movie_ids)
        AND rating_im >= 0.8
      GROUP BY userID
      ORDER BY num_shared DESC
      LIMIT @top_k
    ),
    recommendations AS (
      SELECT *
      FROM ML.RECOMMEND(
        MODEL {MODEL},
        (SELECT userID FROM similar_users)
      )
    )
    SELECT
      r.movieId,
      m.title,
      m.genres,
      AVG(r.predicted_rating_im_confidence) * 5 AS avg_score,
      COUNT(DISTINCT r.userID) AS recommended_by
    FROM recommendations r
    JOIN {MOVIES_TABLE} m
      ON r.movieId = CAST(m.movieID AS INT64)
    WHERE r.movieId NOT IN UNNEST(@movie_ids)
    GROUP BY r.movieId, m.title, m.genres
    ORDER BY recommended_by DESC, avg_score DESC
    LIMIT @num_recs
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("movie_ids", "INT64", [int(m) for m in selected_movie_ids]),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
            bigquery.ScalarQueryParameter("num_recs", "INT64", num_recs),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def get_generic_recommendations(num_recs=20):
    """
    Fallback function for when no movies are selected.
    Returns the most popular, highly-rated movies overall.
    """
    query = f"""
    SELECT
      r.movieId,
      m.title,
      m.genres,
      AVG(r.rating_im) * 5 AS avg_score,
      COUNT(r.userID) AS recommended_by
    FROM {RATINGS_TABLE} r
    JOIN {MOVIES_TABLE} m
      ON r.movieId = CAST(m.movieID AS INT64)
    GROUP BY r.movieId, m.title, m.genres
    HAVING recommended_by >= 50
    ORDER BY avg_score DESC, recommended_by DESC
    LIMIT @num_recs
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("num_recs", "INT64", num_recs),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


# --- Example usage ---
if __name__ == "__main__":
    # Simulate a cold start user who selects movies 1, 3, 5, 7
    selected_movies = [1, 3, 5, 7]

    print("=== Finding similar users ===")
    similar = find_similar_users(selected_movies)
    print(similar)

    print("\n=== Top recommendations ===")
    recs = get_recommendations(selected_movies)
    print(recs)

    print("\n=== Generic Recommendations ===")
    generic_recs = get_generic_recommendations()
    print(generic_recs)
