from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from core.users.models import UserProfile
import pandas as pd
import json
import os
import requests
import random
from pathlib import Path
from .ml_engine import recommend_courses
from .roadmap_engine import get_roadmap_preview, get_roadmap_by_category, search_roadmaps, generate_custom_roadmap_from_skill_names
from .api_services import search_all_platforms
from pymongo import MongoClient
from datetime import datetime


def get_mongo_db():
    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise Exception("MONGO_URI not set")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db_name = os.getenv('MONGO_DB_NAME', 'learnsmart_db')
    return client[db_name]


def load_skills_dataset():
    """Load skills dataset as fallback for recommendations (JSON or CSV)."""
    try:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent / 'skills_dataset'
        json_path = base_dir / 'skills_dataset.json'
        csv_path = base_dir / 'skills_dataset.csv'

        # older layout support
        if not json_path.exists() and not csv_path.exists():
            base_dir = Path(__file__).resolve().parent.parent.parent / 'skills_dataset'
            json_path = base_dir / 'skills_dataset.json'
            csv_path = base_dir / 'skills_dataset.csv'

        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        if csv_path.exists():
            import csv as _csv
            skills = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    skill_name = (row.get('skill_name') or row.get('skill') or '').strip()
                    roadmap_step = (row.get('roadmap_step') or row.get('roadmap_step') or '').strip()

                    # Keep original full record for rich dataset
                    skill = {
                        'skill_name': skill_name,
                        'skill': skill_name,
                        'category': row.get('category', '').strip(),
                        'skill_type': row.get('skill_type', '').strip(),
                        'difficulty_level': int(float(row.get('difficulty_level', 0) or 0)),
                        'learning_time_days': int(float(row.get('learning_time_days', 0) or 0)),
                        'popularity_score': float(row.get('popularity_score', 0) or 0),
                        'job_demand_score': float(row.get('job_demand_score', 0) or 0),
                        'salary_impact_percent': float(row.get('salary_impact_percent', 0) or 0),
                        'future_relevance_score': float(row.get('future_relevance_score', 0) or 0),
                        'learning_resources_quality': float(row.get('learning_resources_quality', 0) or 0),
                        'market_trend': row.get('market_trend', '').strip(),
                        'certification_available': str(row.get('certification_available', '')).strip().lower() in ('true', 'yes', '1'),
                        'prerequisites': [row.get(k).strip() for k in row if k.startswith('prerequisites') and row.get(k) and row.get(k).strip()],
                        'complementary_skills': [row.get(k).strip() for k in row if k.startswith('complementary_skills') and row.get(k) and row.get(k).strip()],
                        'industry_usage': [row.get(k).strip() for k in row if k.startswith('industry_usage') and row.get(k) and row.get(k).strip()],
                        'roadmap_step': roadmap_step,
                    }

                    if skill_name:
                        skills.append(skill)
            return skills
    except Exception:
        pass

    return []


def format_roadmap_skills(roadmap):
    """Normalize roadmap skills into a presentation-friendly list."""
    if not roadmap or not roadmap.get('skills'):
        return []

    formatted = []
    for idx, item in enumerate(roadmap.get('skills', []), start=1):
        if isinstance(item, dict):
            skill_name = item.get('skill') or item.get('skill_name') or item.get('name') or ''
            formatted.append({
                'step': idx,
                'skill': skill_name,
                'description': item.get('description', ''),
                'days': item.get('learning_time_days', item.get('days', 0)),
                'difficulty': item.get('difficulty_level', item.get('difficulty', 0)),
            })
        else:
            formatted.append({'step': idx, 'skill': str(item), 'description': '', 'days': 0, 'difficulty': 0})
    return formatted


def normalize_recommended_roadmap(raw_roadmap):
    """Ensure any roadmap source is formatted for template consumption."""
    if isinstance(raw_roadmap, dict):
        return format_roadmap_skills(raw_roadmap)

    if isinstance(raw_roadmap, list):
        if raw_roadmap and isinstance(raw_roadmap[0], dict):
            # roadmap_engine returns list of skill dicts (skill_name, etc)
            if 'skill_name' in raw_roadmap[0] or 'skill' in raw_roadmap[0]:
                return format_roadmap_skills({'skills': raw_roadmap})

        if raw_roadmap and isinstance(raw_roadmap[0], str):
            # FastAPI returns basic strings; convert to step records for template
            return [
                {
                    'step': idx + 1,
                    'skill': s,
                    'description': s,
                    'days': 7,
                    'difficulty': 2,
                }
                for idx, s in enumerate(raw_roadmap)
            ]

        # assume already normalized list of steps.
        return raw_roadmap

    return []


def default_roadmap():
    return [
        {'step': 1, 'skill': 'Learn core fundamentals', 'description': 'Understand key concepts', 'days': 7, 'difficulty': 1},
        {'step': 2, 'skill': 'Build a sample project', 'description': 'Apply what you learned', 'days': 14, 'difficulty': 2},
        {'step': 3, 'skill': 'Practice through guided exercises', 'description': 'Reinforce skills', 'days': 14, 'difficulty': 2},
        {'step': 4, 'skill': 'Review & optimize workflow', 'description': 'Improve efficiency', 'days': 7, 'difficulty': 2},
        {'step': 5, 'skill': 'Explore advanced concepts', 'description': 'Expand mastery', 'days': 21, 'difficulty': 3},
    ]


def merge_roadmaps(api_roadmap, dataset_roadmap, max_steps=8):
    combined = (api_roadmap or []) + (dataset_roadmap or [])
    unique = []
    seen = set()

    for item in combined:
        key = ''
        if isinstance(item, dict):
            key = str(item.get('skill') or item.get('title') or '')
        else:
            key = str(item)
        key = key.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)

    # Sort by difficulty (asc), then step (asc)
    def _sort_key(it):
        if isinstance(it, dict):
            return (int(it.get('difficulty', 9999) or 9999), int(it.get('step', 9999) or 9999))
        return (9999, 9999)

    unique.sort(key=_sort_key)
    return unique[:max_steps]


def generate_roadmap_from_dataset(skills_list, dataset):
    """Generate a detailed roadmap from skills using the dataset."""
    if not skills_list:
        return []

    if not dataset:
        return [{"step": i + 1, "skill": skill, "description": f"Master {skill}", "days": 21, "difficulty": 2} for i, skill in enumerate(skills_list[:5])]

    roadmap_steps = []
    step_counter = 1

    # Collect provider rows for requested skills (support both old and simple CSV format)
    lower_skills = [s.lower() for s in skills_list]

    matched_rows = []
    for row in dataset:
        candidate = (row.get('skill_name') or row.get('skill') or '').strip()
        if candidate and any(candidate.lower() == s for s in lower_skills):
            matched_rows.append(row)

    if not matched_rows:
        # Fallback to partial match if exact fails.
        for row in dataset:
            candidate = (row.get('skill_name') or row.get('skill') or '').strip().lower()
            if candidate and any(s in candidate or candidate in s for s in lower_skills):
                matched_rows.append(row)

    for row in matched_rows[:20]:
        roadmap_step_label = row.get('roadmap_step') or row.get('skill_name') or row.get('skill')
        if roadmap_step_label:
            roadmap_steps.append({
                'step': step_counter,
                'skill': roadmap_step_label,
                'description': f"{roadmap_step_label}",
                'days': int(row.get('learning_time_days', 21) or 21),
                'difficulty': int(row.get('difficulty_level', 2) or 2),
            })
            step_counter += 1
            continue

        # fallback if no roadmap_step values
        skill_name = row.get('skill_name') or row.get('skill')
        if skill_name:
            roadmap_steps.append({
                'step': step_counter,
                'skill': skill_name,
                'description': f"Learn {skill_name}",
                'days': int(row.get('learning_time_days', 21) or 21),
                'difficulty': int(row.get('difficulty_level', 2) or 2),
            })
            step_counter += 1

    if not roadmap_steps:
        return [{"step": i + 1, "skill": skill, "description": f"Master {skill}", "days": 21, "difficulty": 2} for i, skill in enumerate(skills_list[:5])]

    return roadmap_steps


@require_http_methods(["GET", "POST"])
def home_view(request):
    """Home page with skills input and personalized recommendations."""
    # Allow both authenticated and anonymous users
    profile = None
    if request.user.is_authenticated:
        profile = UserProfile.objects.filter(user=request.user).first()
    
    # Handle skill input submission
    if request.method == 'POST':
        skills_input = request.POST.get('skills', '').strip()
        if skills_input:
            skills_list = [s.strip() for s in skills_input.split(',') if s.strip()]
            if profile:
                profile.skills = skills_list
                profile.save()
            return redirect('home')
    
    # Get user skills/interests (comma-separated string expected)
    raw_skills = profile.skills if profile and profile.skills else ''
    if isinstance(raw_skills, str):
        skills = [s.strip() for s in raw_skills.split(',') if s.strip()]
    elif isinstance(raw_skills, list):
        skills = [s.strip() for s in raw_skills if str(s).strip()]
    else:
        skills = []

    raw_interests = profile.interests if profile and profile.interests else ''
    if isinstance(raw_interests, str):
        interests = [i.strip() for i in raw_interests.split(',') if i.strip()]
    elif isinstance(raw_interests, list):
        interests = [i.strip() for i in raw_interests if str(i).strip()]
    else:
        interests = []

    has_skills = bool(skills or interests)
    recommendations = {}
    recommended_courses = []
    recommended_skills = []
    recommended_roadmap = []
    
    # If user has skills, fetch recommendations from FastAPI
    if has_skills and request.user.is_authenticated:
        FASTAPI_URL = os.getenv("FASTAPI_RECOMMENDATION_URL")
        payload = {
            'user_id': str(request.user.id),
            'skills': skills,
            'interests': interests,
            'top_n': 5,
        }
        
        try:
            resp = requests.post(
                f"{FASTAPI_URL}/recommend",
                    json={
                        "skills": skills,
                        "interests": interests
            },
            timeout=10
            )
            resp.raise_for_status()
            recommendations = resp.json()
            recommended_courses = recommendations.get('courses', [])
            recommended_skills = recommendations.get('skills', [])
            
            # FastAPI returns roadmap as list of strings directly from CSV
            api_roadmap_raw = recommendations.get('roadmap', [])
            recommended_roadmap = normalize_recommended_roadmap(api_roadmap_raw)

        except Exception as e:
            # Direct dataset fallback - no complex logic
            recommended_roadmap = []
            recommended_courses = []
            recommended_skills = []
        
        # Always ensure we have a roadmap at this point
        if not recommended_roadmap:
            dataset = load_skills_dataset()
            if not dataset.empty:
                roadmap_list = generate_roadmap_from_dataset(skills, dataset)
                recommended_roadmap = normalize_recommended_roadmap({'skills': roadmap_list})
        
        # Final fallback
        if not recommended_roadmap:
            recommended_roadmap = default_roadmap()
    
    # Collect per-roadmap skill course recommendations as fallback feature
    recommended_roadmap_courses = {}
    if recommended_roadmap:
        try:
            for item in recommended_roadmap[:8]:  # limit processing to first 8 roadmap steps
                skill_name = (item.get('skill') if isinstance(item, dict) else str(item)).strip()
                if not skill_name:
                    continue
                api_results = search_all_platforms(skill_name)
                courses = []
                for source in ('youtube', 'udemy', 'microsoft_learn', 'coursera'):
                    platform_courses = api_results.get(source, [])
                    for c in platform_courses[:2]:
                        courses.append({
                            'title': c.get('title') or c.get('name') or skill_name,
                            'url': c.get('url', '#'),
                            'platform': source,
                        })
                courses = courses[:5]
                recommended_roadmap_courses[skill_name] = courses

            for item in recommended_roadmap:
                skill_name = (item.get('skill') if isinstance(item, dict) else str(item)).strip() if item else ''
                if skill_name:
                    item['recommended_courses'] = recommended_roadmap_courses.get(skill_name, [])
                else:
                    item['recommended_courses'] = []
        except Exception:
            recommended_roadmap_courses = {}

    # Store merged roadmap results for this user into MongoDB (authenticated users only)
    if request.user.is_authenticated:
        try:
            db = get_mongo_db()
            rec_coll = db['recommendations']
            rec_coll.update_one(
                {'user_id': str(request.user.id)},
                {'$set': {
                    'user_id': str(request.user.id),
                    'skills': skills,
                    'interests': interests,
                    'roadmap': recommended_roadmap,
                    'updated_at': datetime.utcnow(),
                }},
                upsert=True
            )
        except Exception:
            pass

    # Get 6-9 random roadmaps for interactive section
    all_roadmaps = get_roadmap_preview(limit=50)  # Get more to pick from
    roadmaps = []
    if all_roadmaps and len(all_roadmaps) > 0:
        try:
            count = min(random.randint(6, 9), len(all_roadmaps))
            roadmaps = random.sample(all_roadmaps, count) if count > 0 else []
        except Exception:
            roadmaps = all_roadmaps[:9]  # Fallback: just take first 9
    
    return render(request, "index.html", {
        "roadmaps": roadmaps,
        "user_profile": profile,
        "user": request.user,
        "user_skills": skills,
        "user_interests": interests,
        "has_skills": has_skills,
        "recommendations": recommendations,
        "recommended_courses": recommended_courses,
        "recommended_skills": recommended_skills,
        "recommended_roadmap": recommended_roadmap,
        "recommended_roadmap_courses": recommended_roadmap_courses,
    })



def custom_roadmap_view(request):
    """Generate a custom roadmap from comma-separated skill names provided via GET param `skills`.

    Renders `roadmap_detail.html` with the generated roadmap.
    """
    skills_param = request.GET.get("skills", "")
    if not skills_param:
        return render(request, "roadmap_detail.html", {"roadmap": None, "error": "No skills provided"})

    skill_names = [s.strip() for s in skills_param.split(",") if s.strip()]
    roadmap = generate_custom_roadmap_from_skill_names(skill_names)
    if not roadmap:
        return render(request, "roadmap_detail.html", {"roadmap": None, "error": "Could not generate roadmap"})
    return render(request, "roadmap_detail.html", {"roadmap": roadmap})


def roadmap_detail_view(request, category_slug):
    """Detail view for a specific roadmap (by category slug).
    
    Note: Recommendations are loaded asynchronously via JavaScript to avoid
    blocking the page load with multiple API calls. The view returns the roadmap
    structure quickly, then JavaScript fetches recommendations for each skill.
    """
    roadmap = get_roadmap_by_category(category_slug)
    if not roadmap:
        return render(request, "roadmap_detail.html", {"roadmap": None, "error": "Roadmap not found"})
    
    # Return roadmap WITHOUT recommendations (they'll be loaded asynchronously)
    # This allows the page to render instantly instead of waiting for API calls
    return render(request, "roadmap_detail.html", {"roadmap": roadmap})


def search_view(request):
    """Search courses (from APIs) and roadmaps by query."""
    query = request.GET.get("q", "").strip()
    type_filter = request.GET.get("type", "all")  # all, courses, roadmaps
    
    # initialize structure with all four platforms so templates can safely iterate
    api_courses = {
        "youtube": [],
        "udemy": [],
        "microsoft_learn": [],
        "coursera": []
    }
    roadmaps = []
    search_roadmap = []
    roadmap_courses = {}
    
    if query:
        # Generate personalized roadmap from the search query (treat as skill)
        dataset = load_skills_dataset()
        if dataset and len(dataset) > 0:
            roadmap_list = generate_roadmap_from_dataset([query], dataset)
            search_roadmap = normalize_recommended_roadmap({'skills': roadmap_list})
            
            # Get courses for each roadmap step
            if search_roadmap:
                try:
                    for item in search_roadmap[:8]:
                        skill_name = (item.get('skill') if isinstance(item, dict) else str(item)).strip()
                        if not skill_name:
                            continue
                        api_results = search_all_platforms(skill_name)
                        courses = []
                        for source in ('youtube', 'udemy', 'microsoft_learn', 'coursera'):
                            platform_courses = api_results.get(source, [])
                            for c in platform_courses[:2]:
                                courses.append({
                                    'title': c.get('title') or c.get('name') or skill_name,
                                    'url': c.get('url', '#'),
                                    'platform': source,
                                })
                        roadmap_courses[skill_name] = courses[:5]
                        item['recommended_courses'] = roadmap_courses[skill_name]
                except Exception:
                    pass
        
        # Always show matching roadmaps for any query type (all/courses/roadmaps) to improve discoverability
        if type_filter in ("all", "courses", "roadmaps"):
            roadmaps = search_roadmaps(query, limit=20)

        # Fallback: if no roadmap matches by query, show the top roadmaps so screen is not empty
        if not roadmaps:
            roadmaps = get_roadmap_preview(limit=12)

        if type_filter in ("all", "courses"):
            # Search APIs for external courses
            api_results = search_all_platforms(query)
            api_courses = {
                "youtube": api_results.get("youtube", []),
                "udemy": api_results.get("udemy", []),
                "microsoft_learn": api_results.get("microsoft_learn", []),
                # coursera was omitted previously because the API had been unreliable;
                # include it now so that any valid data (or mock fallback) is rendered
                "coursera": api_results.get("coursera", [])
            }
    
    return render(
        request,
        "search_results.html",
        {
            "query": query,
            "type_filter": type_filter,
            "api_courses": api_courses,
            "roadmaps": roadmaps,
            "search_roadmap": search_roadmap,
            "roadmap_courses": roadmap_courses,
            "has_results": bool(any(api_courses.values()) or roadmaps or search_roadmap),
        },
    )



def get_skill_recommendations_api(request):
    """API endpoint to fetch recommendations for a single skill.
    
    Called via AJAX from roadmap/search pages to load recommendations asynchronously.
    This prevents blocking the page load with sequential API calls.
    
    Query parameters:
        skill_name (str): The skill name to search for
    
    Returns:
        JSON with keys: youtube, udemy, microsoft_learn (each with top 3 results)
    """
    skill_name = request.GET.get("skill_name", "").strip()
    if not skill_name:
        return JsonResponse({"error": "skill_name required"}, status=400)
    
    try:
        api_results = search_all_platforms(skill_name)
        return JsonResponse({
            "youtube": api_results.get("youtube", [])[:3],
            "udemy": api_results.get("udemy", [])[:3],
            "coursera": api_results.get("coursera", [])[:3],
            "microsoft_learn": api_results.get("microsoft_learn", [])[:3],
            "success": True
        })
    except Exception as e:
        return JsonResponse({
            "youtube": [],
            "udemy": [],
            "coursera": [],
            "microsoft_learn": [],
            "success": False,
            "error": str(e)
        })


def recommend_view(request):
    """Show personalized course recommendations from YouTube, Udemy, and Microsoft Learn.
    
    Accepts query parameter 'skills' to search for courses on that specific skill.
    If no query is provided, uses user's profile skills or defaults to 'python'.
    NOTE: Coursera API was removed due to 405 errors
    """
    # Get skills from search query or user profile
    search_query = request.GET.get("skills", "").strip()
    user_skills = search_query
    user_goal = ""
    
    # If no search query, use user's profile skills
    if not search_query and request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            user_skills = profile.skills or "python"
            user_goal = profile.goal or ""
        except UserProfile.DoesNotExist:
            user_skills = "python"
    elif not search_query:
        user_skills = "python"
    
    # Use the API services to search across platforms
    courses_data = search_all_platforms(user_skills)

    # Tie in roadmaps based on the same skills query
    roadmap_suggestions = []
    try:
        roadmap_suggestions = search_roadmaps(user_skills, limit=6) if user_skills else []
    except Exception:
        roadmap_suggestions = []

    return render(request, "recommendations.html", {
        "user_skills": user_skills,
        "user_goal": user_goal,
        "youtube_courses": courses_data.get("youtube", []),
        "udemy_courses": courses_data.get("udemy", []),
        "microsoft_learn_courses": courses_data.get("microsoft_learn", []),
        "coursera_courses": courses_data.get("coursera", []),
        "recommended_roadmaps": roadmap_suggestions,
        "query": user_skills,
        "search_query": search_query,
    })


def fetch_fastapi_recommendations(request):
    user_id = request.GET.get("user_id")
    if not user_id:
        return JsonResponse({"error": "user_id query parameter required"}, status=400)

    fastapi_url = os.getenv("FASTAPI_RECOMMENDATION_URL", "http://localhost:8001/recommendations")
    payload = {"user_id": user_id, "top_n": 5}

    try:
        response = requests.post(fastapi_url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return JsonResponse({"error": "Timeout contacting recommendation service"}, status=504)
    except requests.exceptions.ConnectionError:
        return JsonResponse({"error": "Cannot connect to recommendation service"}, status=502)
    except requests.exceptions.HTTPError as e:
        status_code = response.status_code if response is not None else 502
        return JsonResponse({"error": "Recommendation service returned error", "details": response.text[:512]}, status=status_code)
    except Exception as e:
        return JsonResponse({"error": "Unexpected error", "details": str(e)}, status=500)

    try:
        data = response.json()
    except ValueError:
        return JsonResponse({"error": "Invalid JSON response from recommendation service"}, status=502)

    return JsonResponse(data, status=response.status_code)

