import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field
import pandas as pd
from pathlib import Path


class RecommendRequest(BaseModel):
    user_id: str = Field(..., description='User ID to generate recommendations for')
    skills: Optional[List[str]] = Field(default_factory=list, description='User skills')
    interests: Optional[List[str]] = Field(default_factory=list, description='User interests')
    top_n: int = Field(5, ge=1, le=20, description='Number of top recommendations')


class RecommendationItem(BaseModel):
    course_id: str
    title: str
    score: float


class RecommendationResponse(BaseModel):
    user_id: str
    skills: List[str]
    interests: List[str]
    courses: List[RecommendationItem]
    roadmap: List[str]
    generated_at: datetime


def load_skills_dataset():
    """Load skills dataset from CSV file."""
    csv_paths = [
        Path(__file__).resolve().parent.parent.parent.parent / 'skills_dataset' / 'skills_dataset.csv',
        Path(__file__).resolve().parent.parent.parent / 'skills_dataset' / 'skills_dataset.csv',
        Path('skills_dataset') / 'skills_dataset.csv',
        Path('skills_dataset/skills_dataset.csv'),
    ]

    for csv_path in csv_paths:
        if csv_path.exists():
            try:
                return pd.read_csv(csv_path)
            except Exception as e:
                print(f"Error loading {csv_path}: {e}")
                continue

    return pd.DataFrame()


app = FastAPI(title='Machine Learning Recommendation API')


@app.get('/')
def index():
    return {'status': 'ok', 'service': 'recommendation-api'}


@app.post('/recommendations')
def recommend(data: dict):
    """Generate recommendations based on user skills using CSV dataset."""
    user_id = data.get('user_id', 'unknown')
    skills = data.get('skills', [])
    interests = data.get('interests', [])

    try:
        df = load_skills_dataset()
    except Exception as e:
        return {
            'user_id': user_id,
            'skills': skills,
            'interests': interests,
            'courses': [],
            'roadmap': [
                'Learn Basics',
                'Practice Projects',
                'Advanced Learning'
            ],
            'error': f'Dataset load error: {str(e)}'
        }

    roadmap = []
    courses = []
    recommended_skills = set()

    # If dataset is empty, return defaults
    if df.empty:
        return {
            'user_id': user_id,
            'skills': skills,
            'interests': interests,
            'courses': [{'course_id': 'default', 'title': 'General Learning Course', 'score': 1.0}],
            'roadmap': [
                'Learn Basics',
                'Practice Projects',
                'Advanced Learning'
            ],
            'generated_at': datetime.utcnow().isoformat()
        }

    # Process each skill against dataset
    for skill in skills:
        if not skill:
            continue

        skill_lower = str(skill).strip().lower()

        # Find matching rows from dataset
        try:
            matches = df[df['skill'].astype(str).str.lower() == skill_lower]
        except Exception:
            matches = pd.DataFrame()

        for _, row in matches.iterrows():
            # Get roadmap step title
            roadmap_step = str(row.get('roadmap_step', row.get('skill', skill))).strip()
            if roadmap_step and roadmap_step not in roadmap:
                roadmap.append(roadmap_step)

            # Get course information
            course_name = str(row.get('course', f'Course for {skill}')).strip()
            courses.append({
                'course_id': course_name.lower().replace(' ', '_'),
                'title': course_name,
                'score': 1.0
            })

            # Add skill to recommended
            skill_name = str(row.get('skill', skill)).strip()
            recommended_skills.add(skill_name)

    # Fallback roadmap if no matches found
    if not roadmap:
        roadmap = [
            'Learn Basics',
            'Practice Projects',
            'Advanced Learning'
        ]

    # Fallback course if no matches found
    if not courses:
        courses = [{'course_id': 'default', 'title': 'General Learning Course', 'score': 1.0}]

    # Limit to top 8 steps
    roadmap = roadmap[:8]

    return {
        'user_id': user_id,
        'skills': list(recommended_skills) if recommended_skills else skills,
        'interests': interests,
        'courses': courses,
        'roadmap': roadmap,
        'generated_at': datetime.utcnow().isoformat()
    }


@app.get('/recommendations/{user_id}')
def get_recommendations(user_id: str):
    """Retrieve recommendations for a user (returns default if not found)."""
    return {
        'user_id': user_id,
        'skills': [],
        'interests': [],
        'courses': [{'course_id': 'default', 'title': 'General Learning Course', 'score': 1.0}],
        'roadmap': [
            'Learn Basics',
            'Practice Projects',
            'Advanced Learning'
        ],
        'generated_at': datetime.utcnow().isoformat()
    }
