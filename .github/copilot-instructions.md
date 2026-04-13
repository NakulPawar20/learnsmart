# PLRS (Personalized Learning Recommendation System) - AI Agent Guidelines

## Project Overview
Django-based learning platform with ML-powered course recommendations and skill-based learning roadmaps. Uses scikit-learn for TF-IDF similarity matching and topological sorting for prerequisite-based skill progression.

## Architecture
- **Core Apps**: `users` (UserProfile with goals/skills), `courses` (Course model with skill_tags), `recommender` (ML engine + roadmap generation), `dashboard` (analytics, TBD)
- **Data Sources**: SQLite database for user/course data, external `skills_dataset/skills_dataset.json` for 1800+ skills metadata
- **ML Pipeline**: `ml_engine.py` uses TF-IDF vectorization on course skill_tags for cosine similarity recommendations
- **Roadmap Engine**: `roadmap_engine.py` performs topological sort on skill prerequisites by category

## Key Patterns
- **Skill Matching**: Store skills as comma-separated strings in `UserProfile.skills` and `Course.skill_tags` (e.g., "python,machine learning,data analysis")
- **Data Loading**: Skills dataset loaded from `../../../skills_dataset/skills_dataset.json` relative to `recommender/` app
- **Template Structure**: All templates in `recommender/templates/`, static files in `recommender/static/recommender/`
- **URL Routing**: Root URLs in `recommender/urls.py`, authentication handled at project level

## Development Workflow
- **Setup**: `pip install -r requirements.txt`, `python manage.py migrate`, populate courses via admin or scripts
- **Data Population**: No fixtures; courses added manually or via custom scripts. Skills data is read-only from JSON file
- **Testing Recommendations**: Use hardcoded skills in `recommend_view()` (currently "python machine learning") for development
- **Static Files**: Served from `recommender/static/`, collect with `python manage.py collectstatic` for production

## Code Conventions
- **ML Integration**: Pandas DataFrames for course data manipulation, sklearn for vectorization/similarity
- **Error Handling**: Graceful fallbacks (empty lists) when datasets unavailable
- **Authentication**: Standard Django auth with custom UserProfile, login redirects to `/recommend/`
- **Search**: Case-insensitive queries on title/platform/skill_tags using Django Q objects

## Common Tasks
- **Add Courses**: Create Course instances with skill_tags matching skills_dataset vocabulary
- **Debug Recommendations**: Check TF-IDF matrix shape and similarity scores in `ml_engine.recommend_courses()`
- **Extend Roadmaps**: Modify `_topological_sort_skills()` for custom ordering logic
- **User Skills**: Parse `UserProfile.skills` as comma-separated values for ML input

## File Reference Examples
- **ML Logic**: [recommender/ml_engine.py](recommender/ml_engine.py) - TF-IDF recommendation engine
- **Roadmap Generation**: [recommender/roadmap_engine.py](recommender/roadmap_engine.py) - Skill prerequisite sorting
- **Data Models**: [courses/models.py](courses/models.py) - Course with skill_tags field
- **Main Views**: [recommender/views.py](recommender/views.py) - Search and recommendation endpoints</content>
<parameter name="filePath">d:\BE-Project PLRS\cursor\cursor\PLRS\.github\copilot-instructions.md