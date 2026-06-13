import os
import requests
import streamlit as st
import re
from concurrent.futures import ThreadPoolExecutor
from streamlit_searchbox import st_searchbox
from google.cloud import bigquery
from google.oauth2 import service_account

BACKEND_URL = "http://127.0.0.1:5000"

def format_title(title):
    if not isinstance(title, str): return title
    match = re.match(r'^(.*?),\s*(The|A|An)(\s*\(\d{4}\))?$', title, flags=re.IGNORECASE)
    if match:
        base, article, year = match.groups()
        return f"{article.capitalize()} {base}{year if year else ''}"
    return title

LANGUAGE_MAP = {
    "en": "English", "fr": "French", "es": "Spanish", "de": "German", 
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "ru": "Russian", "pt": "Portuguese", "hi": "Hindi"
}
REVERSE_LANGUAGE_MAP = {v: k for k, v in LANGUAGE_MAP.items()}

# ── Page config ────────────────────────────────────────────────────
st.set_page_config(
    page_title="MovieLens Explorer",
    page_icon="🎬",
    layout="wide"
)

# ── Custom CSS for a polished look ─────────────────────────────────
st.markdown("""
<style>
    /* Header styling */
    .main-title {
        text-align: center;
        color: #667eea; /* Primary brand color */
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        font-size: 3.5rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
        cursor: pointer;
        transition: opacity 0.3s;
    }
    .main-title:hover {
        opacity: 0.8;
    }
    .sub-title {
        text-align: center;
        color: #888;
        font-size: 1.1rem;
        margin-top: 0;
    }
    /* Card-like containers */
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1rem;
    }
    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e1e2f, #2a2a40);
        border: 1px solid #333;
        border-radius: 12px;
        padding: 1rem;
    }
    /* Movie poster cards */
    .movie-card {
        background: linear-gradient(135deg, #1e1e2f, #2a2a40);
        border: 1px solid #333;
        border-radius: 16px;
        padding: 1rem;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .movie-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
    }
    .movie-card img {
        border-radius: 12px;
        width: 100%;
        max-height: 320px;
        object-fit: cover;
    }
    .movie-card h4 {
        margin: 0.5rem 0 0.25rem;
        font-size: 0.95rem;
        color: #e0e0e0;
    }
    .movie-card p {
        margin: 0;
        font-size: 0.8rem;
        color: #888;
    }
    .selected-pill {
        display: inline-block;
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin: 0.2rem;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ── BigQuery Client Setup ──────────────────────────────────────────
# Uses environment variables for configuration, falling back to ADC on Cloud Run.
BQ_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "movie-recommender-492111")

try:
    # Use ADC by default, but allow local key file for development
    key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if os.path.exists(key_file):
        credentials = service_account.Credentials.from_service_account_file(key_file)
        client = bigquery.Client(project=BQ_PROJECT, credentials=credentials)
    else:
        # On Cloud Run, this will automatically use the service account's identity
        client = bigquery.Client(project=BQ_PROJECT)
except Exception as e:
    st.error(f"Failed to connect to BigQuery: {e}")
    st.stop()

# Dynamic table references based on project
DATASET = os.getenv("BQ_DATASET", "Movies_Dataset")
TABLE = f"`{BQ_PROJECT}.{DATASET}.Movie_Table`"
RATINGS_TABLE = f"`{BQ_PROJECT}.{DATASET}.Ratings_Lists`"


@st.cache_data
def run_query(query):
    """Run a BigQuery SQL query and return results as a DataFrame."""
    df = client.query(query).to_dataframe()
    if 'title' in df.columns:
        df['title'] = df['title'].apply(format_title)
    if 'language' in df.columns:
        df['language'] = df['language'].apply(lambda x: LANGUAGE_MAP.get(str(x).lower(), str(x).upper() if x else 'Unknown'))
    return df


# ── Header ─────────────────────────────────────────────────────────
st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <a href="/" target="_self" style="text-decoration: none;">
            <h1 class="main-title">🎬 MovieLens Explorer</h1>
        </a>
        <p class="sub-title">Explore the MovieLens movie dataset powered by Google BigQuery</p>
    </div>
""", unsafe_allow_html=True)
st.divider()

# ── Sidebar navigation ────────────────────────────────────────────
st.sidebar.title("🧭 Navigation")
page = st.sidebar.radio(
    "Choose a page:",
    [
        "🏠 Home",
        "🔍 Search & Recommend",
        "🎭 Filter by Genre & Language",
        "📊 Genre Breakdown",
        "⭐ Top Rated Movies",
        "📈 Rating Distribution",
        "👥 Top Raters",
    ],
    label_visibility="collapsed"
)


# ══════════════════════════════════════════════════════════════════
#  PAGE: Search & Recommend
# ══════════════════════════════════════════════════════════════════
if page == "🔍 Search & Recommend":
    st.header("🔍 Search & Recommend")
    st.write("Search for a movie to see its details and get personalized recommendations!")

    def fetch_suggestions(searchterm: str):
        if not searchterm:
            return []
        try:
            resp = requests.get(
                f"{BACKEND_URL}/api/autocomplete",
                params={"query": searchterm},
                timeout=5
            )
            suggestions = resp.json()
            return [(format_title(m["title"]), m) for m in suggestions]
        except Exception:
            return []

    # ── Search bar with Dropdown Autocomplete ──
    selected_movie = st_searchbox(
        fetch_suggestions,
        placeholder="Type a movie title... e.g. Toy Story, Matrix",
        key="main_search",
        clear_on_submit=False
    )

    if selected_movie:
        st.divider()
        st.subheader(f"🎬 {format_title(selected_movie['title'])}")
        # Fetch movie details from BigQuery and Poster from TMDb
        with st.spinner("Fetching details..."):
            try:
                p_resp = requests.get(f"{BACKEND_URL}/api/poster", params={"title": selected_movie['title']}, timeout=5)
                p_data = p_resp.json()
                main_poster = p_data.get("poster")
                main_lang_code = p_data.get("language", "Unknown").lower()
                main_lang = LANGUAGE_MAP.get(main_lang_code, main_lang_code.upper() if main_lang_code != "unknown" else "Unknown")
            except Exception:
                main_poster = None
                main_lang = "Unknown"

            query = f"""
                SELECT m.movieID, m.title, m.genres,
                       ROUND(AVG(r.rating_im) * 5, 2) AS avg_rating,
                       COUNT(r.rating_im) AS num_ratings
                FROM {TABLE} m
                LEFT JOIN {RATINGS_TABLE} r ON CAST(m.movieID AS INT64) = r.movieId
                WHERE CAST(m.movieID AS INT64) = {selected_movie['movieID']}
                GROUP BY m.movieID, m.title, m.genres
            """
            
            # Setup columns for header layout
            col1, col2 = st.columns([1, 4])
            
            with col1:
                if main_poster:
                    # Added styling to make main poster look exactly like recommendation posters
                    st.markdown(f'<div class="movie-card" style="padding:0;border:none;background:transparent;box-shadow:none;"><img src="{main_poster}" alt="{selected_movie["title"]}" /></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="movie-card" style="height:280px;display:flex;align-items:center;justify-content:center;color:#666;padding:0;border:none;background:transparent;box-shadow:none;">🎬 No Poster</div>', unsafe_allow_html=True)

            with col2:
                st.write("") # small top margin
                try:
                    df = run_query(query)
                    if not df.empty:
                        avg_rating = df['avg_rating'].iloc[0]
                        num_ratings = df['num_ratings'].iloc[0]
                        st.write(f"**Genres:** {df['genres'].iloc[0]}")
                        st.write(f"**Language:** {main_lang}")
                        st.write(f"**⭐ Average Rating:** {avg_rating} ({num_ratings} ratings)")
                    else:
                        st.write(f"**Genres:** {selected_movie.get('genres', 'N/A')}")
                except Exception:
                    st.write(f"**Genres:** {selected_movie.get('genres', 'N/A')}")

        # ── Get Recommendations ──
        st.subheader("🎯 Because you liked this, we recommend:")
        
        with st.spinner("🤖 AI is finding the best movies for you..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/api/recommendations",
                    json={"movie_ids": [int(selected_movie["movieID"])]},
                    timeout=60
                )
                recs = resp.json()
            except Exception:
                recs = []
                st.error("❌ Could not reach the backend. Make sure `backend.py` is running.")

        if isinstance(recs, list) and len(recs) > 0:
            # Fetch true average ratings from the main dataset for the recommended movies
            movie_ids_str = ", ".join(str(m['movieID']) for m in recs)
            if movie_ids_str:
                try:
                    ratings_query = f"""
                        SELECT movieId, ROUND(AVG(rating_im) * 5, 2) AS avg_rating
                        FROM {RATINGS_TABLE}
                        WHERE CAST(movieId AS INT64) IN ({movie_ids_str})
                        GROUP BY movieId
                    """
                    ratings_df = run_query(ratings_query)
                    ratings_map = dict(zip(ratings_df['movieId'], ratings_df['avg_rating']))  # type: ignore
                except Exception:
                    ratings_map = {}  # type: ignore
            else:
                ratings_map = {}  # type: ignore

            # Display in a responsive grid
            cols = st.columns(4)
            for i, movie in enumerate(recs):
                with cols[i % 4]:
                    poster = movie.get("poster")
                    if poster:
                        poster_img = f'<img src="{poster}" alt="{movie["title"]}" />'
                    else:
                        poster_img = '<div style="height:280px;display:flex;align-items:center;justify-content:center;background:#2a2a40;border-radius:12px;color:#666;">🎬 No Poster</div>'

                    # Use the true DB average rating instead of the ML confidence score
                    true_score = ratings_map.get(movie.get('movieID'), 0)  # type: ignore
                    stars_count = int(round(true_score)) if true_score > 0 else 0
                    stars = "⭐" * min(stars_count, 5)
                    lang = LANGUAGE_MAP.get(str(movie.get('language', '')).lower(), 'Unknown')

                    st.markdown(f"""
                    <div class="movie-card">
                        {poster_img}
                        <h4>{format_title(movie['title'])}</h4>
                        <p>{stars} ({true_score:.1f})</p>
                        <p>{movie.get('genres', 'N/A')}</p>
                        <p style="color:#aaa; font-size:0.75rem;">🌐 {lang}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.write("")  # spacing
        elif not isinstance(recs, list):
            st.error(f"Backend error: {recs}")
    else:
        st.info("👆 Use the search dropdown above to look up a movie!")

# ══════════════════════════════════════════════════════════════════
#  PAGE: Home
# ══════════════════════════════════════════════════════════════════
elif page == "🏠 Home":
    st.header("🏠 Dataset Home")
    st.write("Browse the most iconic and popular movies in the dataset!")

    if "overview_limit" not in st.session_state:
        st.session_state.overview_limit = 50

    try:
        # Load Metrics Automatically
        col1, col2, col3, col4 = st.columns(4)

        total_movies = run_query(f"SELECT COUNT(*) AS cnt FROM {TABLE}")
        unique_genres = run_query(f"""
            SELECT COUNT(DISTINCT genres) AS cnt FROM {TABLE}
        """)
        no_genre = run_query(f"""
            SELECT COUNT(*) AS cnt FROM {TABLE}
            WHERE genres = '(no genres listed)'
        """)
        total_ratings = run_query(f"SELECT COUNT(*) AS cnt FROM {RATINGS_TABLE}")

        col1.metric("🎬 Total Movies", f"{total_movies['cnt'].iloc[0]:,}")
        col2.metric("🎭 Unique Genre Combos", f"{unique_genres['cnt'].iloc[0]:,}")
        col3.metric("❓ No Genre Listed", f"{no_genre['cnt'].iloc[0]:,}")
        col4.metric("⭐ Total Ratings", f"{total_ratings['cnt'].iloc[0]:,}")

        st.divider()

        # Browse movies with posters
        st.subheader("🌟 Popular Movies")
        query = f"""
            SELECT m.movieID, m.title, m.genres,
                   ROUND(AVG(r.rating_im) * 5, 2) AS avg_rating,
                   COUNT(r.rating_im) AS num_ratings
            FROM {TABLE} m
            LEFT JOIN {RATINGS_TABLE} r ON CAST(m.movieID AS INT64) = r.movieId
            GROUP BY m.movieID, m.title, m.genres
            ORDER BY num_ratings DESC
            LIMIT {st.session_state.overview_limit}
        """
        
        with st.spinner("Fetching popular movies and posters..."):
            df = run_query(query)
            
            # Fetch posters and language in parallel to avoid freezing Streamlit
            def fetch_single_poster_and_lang(title):
                try:
                    p_resp = requests.get(f"{BACKEND_URL}/api/poster", params={"title": title}, timeout=3)
                    data = p_resp.json()
                    return data.get("poster"), data.get("language", "Unknown")
                except Exception:
                    return None, "Unknown"

            with ThreadPoolExecutor(max_workers=10) as executor:
                # Returns a list of tuples (poster, lang)
                poster_lang_tuples = list(executor.map(fetch_single_poster_and_lang, df['title'].tolist()))
                
            df['poster'] = [item[0] for item in poster_lang_tuples]
            df['lang'] = [item[1] for item in poster_lang_tuples]

            # Display posters in a 5-column grid
            cols = st.columns(5)
            for i, row in df.iterrows():
                score = row["avg_rating"] if row["avg_rating"] else 0
                stars_count = int(round(score)) if score > 0 else 0
                stars = "⭐" * min(stars_count, 5)
                poster = row['poster']
                lang_display = row.get('language', 'Unknown')
                
                # The API gives us a 2-character language code (e.g., 'en', 'fr') or language string.
                # Use our mapping to render a full name, fallback to whatever we received.
                lang_code = str(row.get('lang', '')).lower()
                lang_display = LANGUAGE_MAP.get(lang_code, row.get('lang', 'Unknown'))
                if not lang_display or lang_display.strip() == '':
                    lang_display = 'Unknown'

                with cols[i % 5]:
                    if poster:
                        poster_img = f'<img src="{poster}" alt="{row["title"]}" />'
                    else:
                        poster_img = '<div style="height:280px;display:flex;align-items:center;justify-content:center;background:#2a2a40;border-radius:12px;color:#666;">🎬 No Poster</div>'

                    st.markdown(f"""
                    <div class="movie-card">
                        {poster_img}
                        <h4>{format_title(row['title'])}</h4>
                        <p>{stars} ({score:.1f})</p>
                        <p>{row.get('genres', 'N/A')}</p>
                        <p style="color:#aaa; font-size:0.75rem;">🌐 {lang_display}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.write("")
        
        # Load More Button
        st.write("")
        col_btn, _, _ = st.columns([1, 2, 2])
        with col_btn:
            if st.button("⬇️ Load More Movies"):
                st.session_state.overview_limit += 50
                st.rerun()

    except Exception as e:
        st.error(f"Query failed: {e}")


# ══════════════════════════════════════════════════════════════════
elif page == "🎭 Filter by Genre & Language":
    st.header("🎭 Filter Movies by Genre & Language")
    st.write("Select genres and/or languages to see matching movies.")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        genres = st.multiselect(
            "Select genre(s):",
            ["Action", "Adventure", "Animation", "Comedy", "Crime",
             "Documentary", "Drama", "Fantasy", "Horror", "Musical",
             "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western"],
            default=["Action"]
        )
    with col2:
        languages = st.multiselect(
            "Select language(s):",
            list(LANGUAGE_MAP.values()),
            default=[]
        )
    with col3:
        max_results = st.number_input("Max results:", min_value=10, max_value=200, value=50, step=10)

    if st.button("🎬 Filter"):
        if not genres and not languages:
            st.warning("⚠️ Please select at least one genre or language.")
        else:
            clauses: list[str] = []
            if genres:
                clauses.append("(" + " OR ".join([f"m.genres LIKE '%{g}%'" for g in genres]) + ")")
            
            where_stmt = " AND ".join(clauses)
            query_limit = max_results * 5 if languages else max_results # Over-fetch for memory filter
            query = f"""
                SELECT m.movieID, m.title, m.genres,
                       ROUND(AVG(r.rating_im) * 5, 2) AS avg_rating,
                       COUNT(r.rating_im) AS num_ratings
                FROM {TABLE} m
                LEFT JOIN {RATINGS_TABLE} r ON CAST(m.movieID AS INT64) = r.movieId
                WHERE {where_stmt if where_stmt else "1=1"}
                GROUP BY m.movieID, m.title, m.genres
                ORDER BY num_ratings DESC
                LIMIT {query_limit}
            """
            with st.spinner("Filtering movies..."):
                df = run_query(query)
                if df.empty:
                    st.warning("No movies found matching your criteria.")
                else:
                    # In-memory language filtering via TMDb
                    if languages:
                        lang_codes = [REVERSE_LANGUAGE_MAP[l].lower() for l in languages]

                        def fetch_movie_lang(title):
                            try:
                                p_resp = requests.get(f"{BACKEND_URL}/api/poster", params={"title": title}, timeout=3)
                                data = p_resp.json()
                                return data.get("language", "Unknown").lower()
                            except Exception:
                                return "unknown"

                        with ThreadPoolExecutor(max_workers=10) as executor:
                            df['api_lang'] = list(executor.map(fetch_movie_lang, df['title'].tolist()))
                        
                        df = df[df['api_lang'].isin(lang_codes)]
                        df = df.drop(columns=['api_lang'])
                        df = df.head(max_results) # Truncate back to exact max_results requested

                    if df.empty:
                         st.warning("No movies found matching your precise language filters.")
                    else:
                         st.success(f"✅ Found **{len(df)}** movie(s):")
                         st.dataframe(df, hide_index=True)


# ══════════════════════════════════════════════════════════════════
#  PAGE: Genre Breakdown
# ══════════════════════════════════════════════════════════════════
elif page == "📊 Genre Breakdown":
    st.header("📊 Genre Breakdown with Ratings")
    st.write("See movie counts and average ratings for each genre combination.")

    top_n = st.slider("Number of top genre combos to show:", 5, 50, 15, step=5)

    if st.button("📊 Show Breakdown", use_container_width=True):
        query = f"""
            SELECT m.genres,
                   COUNT(DISTINCT m.movieID) AS movie_count,
                   ROUND(AVG(r.rating_im) * 5, 2) AS avg_rating,
                   COUNT(r.rating_im) AS total_ratings
            FROM {TABLE} m
            LEFT JOIN {RATINGS_TABLE} r ON CAST(m.movieID AS INT64) = r.movieId
            GROUP BY m.genres
            ORDER BY movie_count DESC
            LIMIT {top_n}
        """
        df = run_query(query)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📋 Table")
            st.dataframe(df, use_container_width=True, hide_index=True)
        with col2:
            st.subheader("📈 Movies per Genre")
            st.bar_chart(df.set_index("genres")["movie_count"])





# ══════════════════════════════════════════════════════════════════
#  PAGE: Top Rated Movies
# ══════════════════════════════════════════════════════════════════
elif page == "⭐ Top Rated Movies":
    st.header("⭐ Top Rated Movies")
    st.write("Discover the highest-rated movies based on user ratings.")

    col1, col2 = st.columns(2)
    with col1:
        min_ratings = st.slider("Minimum number of ratings:", 10, 1000, 100, step=10)
    with col2:
        top_n = st.slider("Number of movies to show:", 10, 100, 25, step=5)

    if st.button("⭐ Show Top Rated", use_container_width=True):
        query = f"""
            SELECT m.movieID, m.title, m.genres,
                   ROUND(AVG(r.rating_im) * 5, 2) AS avg_rating,
                   COUNT(r.rating_im) AS num_ratings
            FROM {TABLE} m
            INNER JOIN {RATINGS_TABLE} r ON CAST(m.movieID AS INT64) = r.movieId
            GROUP BY m.movieID, m.title, m.genres
            HAVING COUNT(r.rating_im) >= {min_ratings}
            ORDER BY avg_rating DESC, num_ratings DESC
            LIMIT {top_n}
        """
        df = run_query(query)

        if df.empty:
            st.warning("No movies meet the minimum rating count threshold.")
        else:
            st.success(f"✅ Top **{len(df)}** movies with at least **{min_ratings}** ratings:")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.subheader("📊 Average Rating")
            st.bar_chart(df.set_index("title")["avg_rating"].head(15))


# ══════════════════════════════════════════════════════════════════
#  PAGE: Rating Distribution
# ══════════════════════════════════════════════════════════════════
elif page == "📈 Rating Distribution":
    st.header("📈 Rating Distribution")
    st.write("See how users rate movies across the entire dataset.")

    if st.button("📈 Show Distribution", use_container_width=True):
        # Overall stats
        stats = run_query(f"""
            SELECT
                ROUND(AVG(rating_im) * 5, 2) AS avg_rating,
                ROUND(STDDEV(rating_im) * 5, 2) AS std_dev,
                COUNT(*) AS total_ratings,
                COUNT(DISTINCT userID) AS unique_users,
                COUNT(DISTINCT movieId) AS rated_movies
            FROM {RATINGS_TABLE}
        """)

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("⭐ Avg Rating", stats["avg_rating"].iloc[0])
        col2.metric("📏 Std Dev", stats["std_dev"].iloc[0])
        col3.metric("📝 Total Ratings", f"{stats['total_ratings'].iloc[0]:,}")
        col4.metric("👥 Unique Users", f"{stats['unique_users'].iloc[0]:,}")
        col5.metric("🎬 Rated Movies", f"{stats['rated_movies'].iloc[0]:,}")

        st.divider()

        # Distribution of rating values
        st.subheader("Distribution of Rating Values")
        dist = run_query(f"""
            SELECT ROUND(rating_im * 5, 1) AS rating_score, COUNT(*) AS count
            FROM {RATINGS_TABLE}
            GROUP BY rating_score
            ORDER BY rating_score
        """)
        st.bar_chart(dist.set_index("rating_score")["count"])

        # Ratings per movie stats
        st.subheader("Ratings per Movie")
        rpm = run_query(f"""
            SELECT
                ROUND(AVG(cnt), 0) AS avg_per_movie,
                MAX(cnt) AS max_per_movie,
                MIN(cnt) AS min_per_movie
            FROM (
                SELECT movieId, COUNT(*) AS cnt
                FROM {RATINGS_TABLE}
                GROUP BY movieId
            )
        """)
        col1, col2, col3 = st.columns(3)
        col1.metric("Average Ratings/Movie", f"{rpm['avg_per_movie'].iloc[0]:,.0f}")
        col2.metric("Max Ratings on a Movie", f"{rpm['max_per_movie'].iloc[0]:,}")
        col3.metric("Min Ratings on a Movie", f"{rpm['min_per_movie'].iloc[0]:,}")


# ══════════════════════════════════════════════════════════════════
#  PAGE: Top Raters
# ══════════════════════════════════════════════════════════════════
elif page == "👥 Top Raters":
    st.header("👥 Most Active Raters")
    st.write("See which users have submitted the most ratings.")

    top_n = st.slider("Number of users to show:", 10, 100, 25, step=5)

    if st.button("👥 Show Top Raters", use_container_width=True):
        query = f"""
            SELECT userID,
                   COUNT(*) AS num_ratings,
                   ROUND(AVG(rating_im) * 5, 2) AS avg_rating,
                   ROUND(MIN(rating_im) * 5, 2) AS min_rating,
                   ROUND(MAX(rating_im) * 5, 2) AS max_rating
            FROM {RATINGS_TABLE}
            GROUP BY userID
            ORDER BY num_ratings DESC
            LIMIT {top_n}
        """
        df = run_query(query)

        st.success(f"✅ Top **{len(df)}** most active raters:")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("📊 Number of Ratings per User")
        st.bar_chart(df.set_index("userID")["num_ratings"].head(15))


# ── Footer ─────────────────────────────────────────────────────────
st.divider()
st.caption("Built with Streamlit & Google BigQuery • MovieLens Dataset")