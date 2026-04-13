"""
Roadmap generation engine using the skills dataset.
Loads skills from skills_dataset and generates structured learning roadmaps by category.
"""
import csv
import json
from pathlib import Path
from collections import defaultdict


# Root dataset paths - prefer JSON, fallback CSV
DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "skills_dataset"
SKILLS_JSON_PATH = DATASET_DIR / "skills_dataset.json"
SKILLS_CSV_PATH = DATASET_DIR / "skills_dataset.csv"


def _parse_csv_skill_row(row):
    """Convert one CSV row dict to structured skill dict."""
    skill = {
        "skill_name": row.get("skill_name", "").strip(),
        "category": row.get("category", "").strip(),
        "skill_type": row.get("skill_type", "").strip(),
    }

    def parse_int(key):
        try:
            return int(float(row.get(key, "") or 0))
        except (ValueError, TypeError):
            return 0

    def parse_float(key):
        try:
            return float(row.get(key, "") or 0)
        except (ValueError, TypeError):
            return 0.0

    skill["difficulty_level"] = parse_int("difficulty_level")
    skill["learning_time_days"] = parse_int("learning_time_days")
    skill["popularity_score"] = parse_float("popularity_score")
    skill["job_demand_score"] = parse_float("job_demand_score")
    skill["salary_impact_percent"] = parse_float("salary_impact_percent")
    skill["future_relevance_score"] = parse_float("future_relevance_score")
    skill["learning_resources_quality"] = parse_float("learning_resources_quality")

    def parse_bool(key):
        value = str(row.get(key, "")).strip().lower()
        return value in ("true", "yes", "1")

    skill["certification_available"] = parse_bool("certification_available")
    skill["market_trend"] = row.get("market_trend", "").strip()

    # Collect list columns
    skill["prerequisites"] = [v.strip() for k, v in row.items() if k.startswith("prerequisites") and v and v.strip()] if row else []
    skill["complementary_skills"] = [v.strip() for k, v in row.items() if k.startswith("complementary_skills") and v and v.strip()] if row else []
    skill["industry_usage"] = [v.strip() for k, v in row.items() if k.startswith("industry_usage") and v and v.strip()] if row else []

    return skill


def load_skills_dataset():
    """Load skills from JSON or CSV dataset. Returns list of skill dicts."""
    # Attempt JSON first
    if SKILLS_JSON_PATH.exists():
        try:
            with open(SKILLS_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Fallback to CSV
    if SKILLS_CSV_PATH.exists():
        skills = []
        try:
            with open(SKILLS_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    skill = _parse_csv_skill_row(row)
                    if skill.get("skill_name"):
                        skills.append(skill)
            return skills
        except Exception:
            return []

    return []


def _collect_prerequisites(skill):
    """Extract prerequisites from a skill. Returns list of prerequisite skill names."""
    prereqs = skill.get("prerequisites") or []
    if isinstance(prereqs, list):
        return [p for p in prereqs if p and isinstance(p, str)]
    return []


def _topological_sort_skills(skills_list):
    """
    Order skills by prerequisites (topological sort).
    Skills with no prerequisites come first, then skills whose prereqs are satisfied.
    Falls back to difficulty_level when order is ambiguous.
    """
    if not skills_list:
        return []
    
    skill_map = {s["skill_name"]: s for s in skills_list}
    in_degree = {s["skill_name"]: 0 for s in skills_list}
    dependents = defaultdict(list)  # prereq -> [skills that depend on it]
    
    for skill in skills_list:
        name = skill["skill_name"]
        prereqs = _collect_prerequisites(skill)
        for prereq in prereqs:
            if prereq in skill_map and prereq != name:
                in_degree[name] += 1
                dependents[prereq].append(name)
    
    result = []
    ready = [n for n in skill_map if in_degree[n] == 0]
    ready.sort(key=lambda n: (skill_map[n]["difficulty_level"], skill_map[n]["learning_time_days"]))
    
    while ready:
        chosen = ready.pop(0)
        result.append(skill_map[chosen])
        for dep in dependents[chosen]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)
        ready.sort(key=lambda n: (skill_map[n]["difficulty_level"], skill_map[n]["learning_time_days"]))
    
    # Append any remaining (cycles or external prereqs) at end, sorted by difficulty
    result_names = {s["skill_name"] for s in result}
    remaining = [s for s in skills_list if s["skill_name"] not in result_names]
    remaining.sort(key=lambda s: (s.get("difficulty_level", 1), s.get("learning_time_days", 0)))
    result.extend(remaining)
    
    return result


def get_roadmaps():
    """
    Generate roadmaps grouped by category.
    Returns list of dicts: {category, description, skills[], total_days, skill_count}
    """
    skills = load_skills_dataset()
    if not skills:
        return []
    
    by_category = defaultdict(list)
    for s in skills:
        cat = s.get("category") or "Other"
        if cat and cat.strip():
            by_category[cat].append(s)
    
    roadmaps = []
    for category, cat_skills in sorted(by_category.items()):
        ordered = _topological_sort_skills(cat_skills)
        total_days = sum(s.get("learning_time_days") or 0 for s in ordered)
        
        roadmaps.append({
            "category": category,
            "slug": _category_to_slug(category),
            "title": category,
            "description": _roadmap_description(category, ordered),
            "skills": ordered,
            "total_days": total_days,
            "skill_count": len(ordered),
            "avg_difficulty": sum(s.get("difficulty_level", 1) for s in ordered) / len(ordered) if ordered else 0,
        })
    
    return sorted(roadmaps, key=lambda r: (r["skill_count"], r["total_days"]), reverse=True)


def _roadmap_description(category, skills):
    """Generate a short description for a roadmap based on its category and skills."""
    if not skills:
        return f"Learn core skills in {category}."
    
    top_skills = [s["skill_name"] for s in skills[:5]]
    if len(skills) > 5:
        return f"Master {category}: {', '.join(top_skills[:3])}, and {len(skills) - 3} more skills."
    return f"Master {category}: {', '.join(top_skills)}."


def _category_to_slug(category):
    """Convert category name to URL slug."""
    if not category:
        return ""
    s = category.lower().replace(" / ", "-").replace(" & ", "-").replace(" ", "-")
    return "".join(c for c in s if c.isalnum() or c == "-").strip("-")


def _slug_to_category(slug, roadmaps=None):
    """Find category from slug. Returns None if not found."""
    roadmaps = roadmaps or get_roadmaps()
    slug_lower = slug.lower().replace("_", "-")
    for r in roadmaps:
        if _category_to_slug(r["category"]) == slug_lower:
            return r["category"]
    return None


def get_roadmap_by_category(category_or_slug):
    """Get a single roadmap by category name or slug."""
    roadmaps = get_roadmaps()
    for r in roadmaps:
        if r["category"] == category_or_slug:
            return r
    category = _slug_to_category(category_or_slug, roadmaps)
    if category:
        return get_roadmap_by_category(category)
    return None


def search_roadmaps(query, limit=20):
    """
    Search roadmaps and skills by query.
    Matches category, skill_name, skill_type, description, prerequisites, complementary_skills.
    Returns list of roadmaps with matching skills, plus individual matching skills.
    """
    if not query or not query.strip():
        return []
    
    q = query.strip().lower()
    skills = load_skills_dataset()
    if not skills:
        return []
    
    # Find roadmaps (categories) that have matching skills
    matching_roadmaps = {}  # category -> {roadmap info + matching_skills}
    matching_skills_standalone = []  # skills that match but we'll group by roadmap
    
    def text_matches(skill, q):
        """Check if skill matches query in any searchable field."""
        fields = [
            skill.get("skill_name") or "",
            skill.get("category") or "",
            skill.get("skill_type") or "",
            skill.get("description") or "",
        ]
        for lst in (skill.get("prerequisites") or [], skill.get("complementary_skills") or [], skill.get("industry_usage") or []):
            if isinstance(lst, list):
                fields.extend(str(x) for x in lst)
        
        text = " ".join(str(f).lower() for f in fields)
        return q in text
    
    for skill in skills:
        if text_matches(skill, q):
            cat = skill.get("category") or "Other"
            if cat not in matching_roadmaps:
                roadmaps_list = get_roadmaps()
                r = next((x for x in roadmaps_list if x["category"] == cat), None)
                if r:
                    matching_roadmaps[cat] = {
                        "category": r["category"],
                        "slug": _category_to_slug(r["category"]),
                        "description": r["description"],
                        "skill_count": r["skill_count"],
                        "total_days": r["total_days"],
                        "matching_skills": [],
                        "match_count": 0,
                    }
            if cat in matching_roadmaps:
                matching_roadmaps[cat]["matching_skills"].append(skill)
                matching_roadmaps[cat]["match_count"] += 1
    
    # If no matching roadmaps by skill-level text matching, check category/description directly
    if not matching_roadmaps:
        all_roadmaps = get_roadmaps()
        for r in all_roadmaps:
            if q in r.get("category", "").lower() or q in r.get("description", "").lower():
                matching_roadmaps[r["category"]] = {
                    "category": r["category"],
                    "slug": r["slug"],
                    "description": r["description"],
                    "skill_count": r["skill_count"],
                    "total_days": r["total_days"],
                    "matching_skills": [],
                    "match_count": 0,
                }

    # Sort by match count, limit results
    result = []
    for r in sorted(matching_roadmaps.values(), key=lambda x: (-x["match_count"], -x["skill_count"]))[:limit]:
        result.append(r)
    
    return result


def get_roadmap_preview(limit=12):
    """Get preview of roadmaps for landing page (top categories by skill count)."""
    roadmaps = get_roadmaps()
    
    # Map category to friendly role name and short description for landing
    role_map = {
        "AI / ML": ("AI/ML Engineer", "Python, ML, deep learning, and AI tools"),
        "Data Science & Analytics": ("Data Scientist", "Python, statistics, visualization, and analytics"),
        "CSE": ("Software Engineer", "Programming, DSA, and system design"),
        "DevOps": ("DevOps Engineer", "CI/CD, containers, cloud, and automation"),
        "Cybersecurity": ("Cybersecurity Analyst", "Security, penetration testing, and compliance"),
        "UI/UX": ("UI/UX Designer", "Design systems, prototyping, and user research"),
        "Programming & Technical Skills": ("Full Stack Developer", "Frontend, backend, and full-stack skills"),
        "Business & Management": ("Product Manager", "Strategy, Agile, and stakeholder management"),
    }
    
    result = []
    for r in roadmaps[:limit]:
        role_info = role_map.get(r["category"])
        title = role_info[0] if role_info else r["category"]
        short_desc = role_info[1] if role_info else r["description"][:80] + "..." if len(r["description"]) > 80 else r["description"]
        result.append({
            "category": r["category"],
            "slug": _category_to_slug(r["category"]),
            "title": title,
            "description": short_desc,
            "skill_count": r["skill_count"],
            "total_days": r["total_days"],
            "popular": r["category"] in ("AI / ML", "Data Science & Analytics", "CSE", "DevOps"),
        })
    return result


def generate_custom_roadmap_from_skill_names(skill_names):
    """Generate a custom roadmap dict from a list of skill name strings.

    The function collects matching skills from the dataset and any prerequisites
    referenced by those skills, then orders them via the topological sorter.
    Unknown skill names are added as simple entries.
    """
    if not skill_names:
        return None

    skills = load_skills_dataset()
    if not skills:
        return None

    skill_map = {s["skill_name"].lower(): s for s in skills if s.get("skill_name")}

    collected = {}

    def collect(name):
        key = name.strip().lower()
        if not key or key in collected:
            return
        if key in skill_map:
            s = skill_map[key]
            collected[s["skill_name"]] = s
            for p in _collect_prerequisites(s):
                collect(p)
        else:
            # create a minimal placeholder skill
            title = name.strip()
            if not title:
                return
            collected[title] = {"skill_name": title, "difficulty_level": 1, "learning_time_days": 1}

    for n in skill_names:
        collect(n)

    skills_list = list(collected.values())
    ordered = _topological_sort_skills(skills_list)
    total_days = sum(s.get("learning_time_days") or 0 for s in ordered)

    return {
        "category": "Custom Roadmap",
        "title": "Custom Roadmap",
        "description": "Roadmap generated from your selected skills.",
        "skills": ordered,
        "total_days": total_days,
        "skill_count": len(ordered),
        "avg_difficulty": sum(s.get("difficulty_level", 1) for s in ordered) / len(ordered) if ordered else 0,
        "is_user_created": True,
    }
