from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def recommend_courses(user_interests, courses_df, top_n=5):
    """
    Recommend courses that best match a user's interests.

    - user_interests: string (comma-separated or free text)
    - courses_df: pandas DataFrame containing at least ['skill_tags', 'categories', 'title']
      skill_tags and categories may be list-like or comma-separated string.

    Returns top_n courses sorted by similarity score.
    """
    if courses_df is None or courses_df.empty:
        return courses_df

    df = courses_df.copy()

    # Ensure tags/categories are strings for vectorization
    def normalize_text(value):
        if isinstance(value, list):
            return ' '.join(map(str, value))
        if value is None:
            return ''
        return str(value)

    df['skill_tags_text'] = df.get('skill_tags', '').apply(normalize_text)
    df['categories_text'] = df.get('categories', '').apply(normalize_text)

    df['combined_text'] = (df['skill_tags_text'] + ' ' + df['categories_text']).str.strip()

    # Fallback to title/description if combined text is sparse
    if df['combined_text'].replace('', float('nan')).isna().all():
        df['combined_text'] = df.get('title', '').fillna('') + ' ' + df.get('description', '').fillna('')

    vectorizer = TfidfVectorizer(stop_words='english', max_features=2048)
    tfidf_matrix = vectorizer.fit_transform(df['combined_text'])

    query = normalize_text(user_interests)
    if not query.strip():
        return df.sort_values(by='score', ascending=False).head(top_n) if 'score' in df else df.head(top_n)

    user_vec = vectorizer.transform([query])
    similarity = cosine_similarity(user_vec, tfidf_matrix).flatten()

    df['score'] = similarity
    ranked_df = df.sort_values(by='score', ascending=False).head(top_n)

    return ranked_df.reset_index(drop=True)


