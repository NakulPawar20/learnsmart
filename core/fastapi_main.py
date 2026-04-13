import os
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RecommendationItem(BaseModel):
    course_id: str
    title: str
    score: float


class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: List[RecommendationItem]
    generated_at: datetime


def get_mongo_client():
    uri = os.getenv('MONGO_HOST', 'mongodb://mongo:27017')
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def flatten_user_text(user_doc: dict) -> str:
    skills = user_doc.get('skills', [])
    interests = user_doc.get('interests', [])
    if isinstance(skills, str):
        skills = [skills]
    if isinstance(interests, str):
        interests = [interests]
    return ' '.join([str(v) for v in skills + interests])


def flatten_course_text(course_doc: dict) -> str:
    parts = []
    parts.append(str(course_doc.get('title', '')))
    parts.append(str(course_doc.get('description', '')))
    tags = course_doc.get('tags', [])
    cats = course_doc.get('categories', [])
    if isinstance(tags, str):
        tags = [tags]
    if isinstance(cats, str):
        cats = [cats]
    parts.extend([str(v) for v in tags + cats])
    return ' '.join(parts).strip()


app = FastAPI(title='FastAPI Recommendation Service')
client = get_mongo_client()
db = client[os.getenv('MONGO_DB_NAME', 'learnsmart_db')]
users_coll = db['users']
courses_coll = db['courses']
rec_coll = db['recommendations']


@app.get('/')
def health():
    return {'status': 'ok'}


@app.get('/recommend/{user_id}', response_model=RecommendationResponse)
def recommend(user_id: str, top_n: int = Field(5, ge=1, le=20)):
    user_doc = users_coll.find_one({'_id': user_id}) or users_coll.find_one({'user_id': user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail='User not found')

    user_text = flatten_user_text(user_doc)
    if not user_text:
        raise HTTPException(status_code=400, detail='User has no skills/interests')

    course_docs = list(courses_coll.find({}))
    if not course_docs:
        raise HTTPException(status_code=404, detail='No courses available')

    corpus = [flatten_course_text(c) for c in course_docs]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=2048)
    try:
        course_matrix = vectorizer.fit_transform(corpus)
        user_vector = vectorizer.transform([user_text])
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f'Failed to vectorize: {e}')

    similarity = cosine_similarity(user_vector, course_matrix)[0]
    ranking = sorted(enumerate(similarity), key=lambda x: x[1], reverse=True)[:top_n]

    recommendations = []
    for idx, score in ranking:
        course = course_docs[idx]
        recommendations.append(RecommendationItem(
            course_id=str(course.get('course_id') or course.get('_id')),
            title=str(course.get('title', 'Untitled')),
            score=float(score)
        ))

    result = RecommendationResponse(
        user_id=user_id,
        recommendations=recommendations,
        generated_at=datetime.utcnow()
    )

    rec_coll.update_one(
        {'user_id': user_id},
        {'$set': {
            'user_id': user_id,
            'results': [r.dict() for r in recommendations],
            'timestamp': datetime.utcnow()
        }},
        upsert=True
    )

    return result
