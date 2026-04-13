# ================================================================
#  NEW FILE: recommender/api_services.py
#  Handles YouTube, Udemy, Microsoft Learn search + Claude AI roadmap
#  NOTE: Coursera API was deprecated due to 405 errors
# ================================================================

import requests, json, re, logging, time
from django.conf import settings
from functools import lru_cache

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
#  CACHING & RATE LIMITING
# ────────────────────────────────────────────────────────────────

# In-memory cache for API responses (skill -> results)
_youtube_cache = {}
_youtube_quota_exhausted = False
_youtube_quota_reset_time = None

# Constants for exponential backoff
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRIES = 2
BACKOFF_MULTIPLIER = 2


# ────────────────────────────────────────────────────────────────
#  YOUTUBE DATA API v3 (PRODUCTION-READY)
#  Get key → https://console.cloud.google.com
#  Steps: New Project → Enable "YouTube Data API v3" → Credentials → Create API Key
# ────────────────────────────────────────────────────────────────

def _is_quota_exhausted(error_dict):
    """
    Check if error is due to quota exceeded.
    
    Args:
        error_dict (dict): Error dict from YouTube API response
    
    Returns:
        bool: True if quotaExceeded, False otherwise
    """
    error_reason = error_dict.get("errors", [{}])[0].get("reason", "")
    return error_reason == "quotaExceeded"

def _is_invalid_key(error_dict):
    """
    Check if error is due to invalid or disabled API key.
    
    Args:
        error_dict (dict): Error dict from YouTube API response
    
    Returns:
        bool: True if invalid key (forbidden access), False otherwise
    """
    error_reason = error_dict.get("errors", [{}])[0].get("reason", "")
    return error_reason in ["forbidden", "keyInvalid", "accessNotConfigured"]

def search_youtube_courses(query: str, max_results: int = 6) -> list:
    """
    Search YouTube for course videos with production-ready error handling.
    
    Features:
    - Caches results per skill (1 request per skill max)
    - Detects and handles 403 quota exceeded errors
    - Detects invalid API key errors
    - Exponential backoff retry (max 2 retries)
    - Timeout=10 seconds per request
    - Logging for debugging
    
    Args:
        query (str): Search query (e.g., "python programming")
        max_results (int): Maximum results to return (default: 6)
    
    Returns:
        list: List of course objects with structure:
            {
                "platform": "youtube",
                "id": "videoId",
                "title": "Video title",
                "channel": "Channel name",
                "thumbnail": "thumbnail_url",
                "views": "1.2M",
                "duration": "4h 26m",
                "url": "https://www.youtube.com/watch?v=...",
                "level": "Beginner|Intermediate|Advanced",
                "free": True,
                "price": "Free"
            }
        Returns empty list if API key is missing, 403 error, or other failures.
    """
    global _youtube_cache, _youtube_quota_exhausted
    
    # ──────────────────────────────────────────────────────────────
    # Check if quota is exhausted (avoid repeated failed requests)
    # ──────────────────────────────────────────────────────────────
    if _youtube_quota_exhausted:
        logger.warning(f"YouTube API quota exhausted. Skipping request for: {query}")
        return []
    
    # ──────────────────────────────────────────────────────────────
    # Check cache first (1 request per unique skill)
    # ──────────────────────────────────────────────────────────────
    if query in _youtube_cache:
        logger.debug(f"Cache HIT for YouTube query: {query}")
        return _youtube_cache[query]
    
    # ──────────────────────────────────────────────────────────────
    # Get API key from Django settings
    # ──────────────────────────────────────────────────────────────
    api_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if not api_key:
        logger.debug("YouTube API key not configured")
        return []
    
    base_url = "https://www.googleapis.com/youtube/v3"
    retry_count = 0
    retry_delay = INITIAL_RETRY_DELAY
    
    # ──────────────────────────────────────────────────────────────
    # Exponential backoff retry loop (max 2 retries)
    # ──────────────────────────────────────────────────────────────
    while retry_count <= MAX_RETRIES:
        try:
            logger.debug(f"YouTube API request #{retry_count + 1} for: {query}")
            
            # Step 1: Search for videos
            search_response = requests.get(
                f"{base_url}/search",
                params={
                    "part": "snippet",
                    "q": f"{query} full course tutorial",
                    "type": "video",
                    "videoDuration": "long",
                    "relevanceLanguage": "en",
                    "maxResults": max_results,
                    "key": api_key,
                },
                timeout=10
            )
            search_response.raise_for_status()
            search_data = search_response.json()
            
            # ──────────────────────────────────────────────────────
            # Check for 403 FORBIDDEN errors
            # ──────────────────────────────────────────────────────
            if "error" in search_data:
                error_dict = search_data.get("error", {})
                error_code = error_dict.get("code")
                error_msg = error_dict.get("message", "Unknown error")
                
                # Handle quota exceeded (stop all future requests)
                if error_code == 403 and _is_quota_exhausted(error_dict):
                    logger.error(f"❌ YouTube API QUOTA EXHAUSTED: {error_msg}")
                    _youtube_quota_exhausted = True
                    return []
                
                # Handle invalid API key (stop all future requests)
                if error_code == 403 and _is_invalid_key(error_dict):
                    logger.error(f"❌ YouTube API KEY INVALID: {error_msg}")
                    _youtube_quota_exhausted = True  # Prevent retry spam
                    return []
                
                # Handle other 403 errors (retry with backoff)
                if error_code == 403:
                    if retry_count < MAX_RETRIES:
                        logger.warning(f"YouTube API 403 error (attempt {retry_count + 1}/{MAX_RETRIES + 1}): {error_msg}. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= BACKOFF_MULTIPLIER
                        retry_count += 1
                        continue
                    else:
                        logger.error(f"YouTube API 403 error after {MAX_RETRIES} retries: {error_msg}")
                        return []
                
                # Log other errors
                logger.error(f"YouTube API error: {error_msg}")
                return []
            
            items = search_data.get("items", [])
            if not items:
                logger.debug(f"No YouTube results found for: {query}")
                # Cache empty results too
                _youtube_cache[query] = []
                return []
            
            # ──────────────────────────────────────────────────────
            # Extract video IDs (batch request, not in loop)
            # ──────────────────────────────────────────────────────
            video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
            
            if not video_ids:
                _youtube_cache[query] = []
                return []
            
            # ──────────────────────────────────────────────────────
            # Step 2: Get video statistics in ONE batch request
            # ──────────────────────────────────────────────────────
            stats_response = requests.get(
                f"{base_url}/videos",
                params={
                    "part": "statistics,contentDetails",
                    "id": ",".join(video_ids),
                    "key": api_key,
                },
                timeout=10
            )
            stats_response.raise_for_status()
            stats_data = stats_response.json()
            
            # Build stats lookup map (efficient, outside any loops)
            stats_map = {
                video["id"]: video 
                for video in stats_data.get("items", [])
            }
            
            # ──────────────────────────────────────────────────────
            # Step 3: Build results with structured format
            # ──────────────────────────────────────────────────────
            results = []
            for item in items:
                try:
                    vid = item["id"]["videoId"]
                    snippet = item["snippet"]
                    stats = stats_map.get(vid, {})
                    
                    view_count = int(stats.get("statistics", {}).get("viewCount", 0))
                    duration = _parse_duration(stats.get("contentDetails", {}).get("duration", ""))
                    
                    results.append({
                        "platform": "youtube",
                        "id": vid,
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("channelTitle", ""),
                        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                        "views": _format_number(view_count),
                        "duration": duration,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "level": _infer_level(snippet.get("title", "")),
                        "free": True,
                        "price": "Free"
                    })
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed YouTube item: {e}")
                    continue
            
            # ──────────────────────────────────────────────────────
            # Success! Cache and return results
            # ──────────────────────────────────────────────────────
            _youtube_cache[query] = results
            logger.info(f"✓ YouTube API success: {len(results)} courses found for '{query}'")
            return results
            
        except requests.exceptions.Timeout:
            if retry_count < MAX_RETRIES:
                logger.warning(f"YouTube API timeout (attempt {retry_count + 1}/{MAX_RETRIES + 1}). Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= BACKOFF_MULTIPLIER
                retry_count += 1
                continue
            else:
                logger.error(f"YouTube API request timed out after {MAX_RETRIES} retries")
                return []
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else "Unknown"
            
            # Handle 403 from HTTPError
            if status_code == 403:
                error_body = e.response.json() if hasattr(e, 'response') else {}
                if _is_quota_exhausted(error_body.get("error", {})):
                    logger.error("❌ YouTube API QUOTA EXHAUSTED")
                    _youtube_quota_exhausted = True
                    return []
                elif _is_invalid_key(error_body.get("error", {})):
                    logger.error("❌ YouTube API KEY INVALID")
                    _youtube_quota_exhausted = True
                    return []
            
            logger.error(f"YouTube API HTTP error {status_code}: {str(e)}")
            return []
        
        except requests.exceptions.RequestException as e:
            if retry_count < MAX_RETRIES:
                logger.warning(f"YouTube API request failed (attempt {retry_count + 1}/{MAX_RETRIES + 1}): {str(e)}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= BACKOFF_MULTIPLIER
                retry_count += 1
                continue
            else:
                logger.error(f"YouTube API request failed after {MAX_RETRIES} retries: {str(e)}")
                return []
        
        except json.JSONDecodeError as e:
            logger.error(f"YouTube API invalid JSON response: {str(e)}")
            return []
        
        except Exception as e:
            logger.error(f"Unexpected YouTube API error: {type(e).__name__}: {str(e)}")
            return []
    
    # This should not be reached, but just in case
    return []


# ────────────────────────────────────────────────────────────────
#  YOUTUBE CACHE & QUOTA MANAGEMENT
# ────────────────────────────────────────────────────────────────

def reset_youtube_cache():
    """Clear the YouTube API response cache (for testing/debugging)."""
    global _youtube_cache
    _youtube_cache.clear()
    logger.info("YouTube cache cleared")

def reset_youtube_quota_flag():
    """Reset the quota exhausted flag (use if quota resets or key is updated)."""
    global _youtube_quota_exhausted
    _youtube_quota_exhausted = False
    logger.info("YouTube quota flag reset. API requests will resume.")

def get_youtube_cache_status():
    """Get cache and quota status (for debugging)."""
    global _youtube_cache, _youtube_quota_exhausted
    return {
        "cached_queries": list(_youtube_cache.keys()),
        "cache_size": len(_youtube_cache),
        "quota_exhausted": _youtube_quota_exhausted,
    }


# ────────────────────────────────────────────────────────────────
#  UDEMY AFFILIATE API
#  Get keys → https://www.udemy.com/developers/affiliate/
#  Steps: Log in → Request Affiliate Access → Copy Client ID & Secret
# ────────────────────────────────────────────────────────────────

def search_udemy_courses(query: str, page_size: int = 6) -> list:
    cid = getattr(settings, "UDEMY_CLIENT_ID", "")
    sec = getattr(settings, "UDEMY_CLIENT_SECRET", "")
    if not cid or not sec:
        return _mock_udemy(query)

    fields = ",".join(["title","url","price","rating","num_reviews",
                        "num_subscribers","instructional_level_simple",
                        "image_480x270","headline","visible_instructors","badges"])
    try:
        r = requests.get("https://www.udemy.com/api-2.0/courses/", params={
            "search": query, "page_size": page_size,
            "ordering": "relevance", "language": "en", "fields[course]": fields,
        }, auth=(cid, sec), headers={"Accept": "application/json"}, timeout=10)
        r.raise_for_status()
        results = []
        for c in r.json().get("results", []):
            instr = (c.get("visible_instructors") or [{}])[0].get("display_name", "")
            badges = c.get("badges") or []
            badge = badges[0].get("badge_family", "") if badges else ""
            price = c.get("price", "")
            try:
                if price and price not in ("Free","0"):
                    price = f"₹{int(float(str(price).replace('$','').replace('₹','')) * 83)}"
            except Exception:
                pass
            results.append({
                "platform": "udemy", "id": str(c.get("id","")),
                "title": c.get("title",""), "instructor": instr,
                "thumbnail": c.get("image_480x270",""),
                "rating": f"{c.get('rating',0):.1f}",
                "students": _format_number(c.get("num_subscribers",0)),
                "price": price or "₹499", "level": c.get("instructional_level_simple","All Levels"),
                "badge": badge, "url": f"https://www.udemy.com{c.get('url','')}",
                "free": price in ("Free","0","₹0"),
            })
        return results
    except Exception as e:
        logger.error(f"Udemy API error: {e}")
        return _mock_udemy(query)


# ────────────────────────────────────────────────────────────────
#  ANTHROPIC CLAUDE AI — Roadmap Generator
#  Get key → https://console.anthropic.com
#  Steps: Sign up → API Keys → Create Key
# ────────────────────────────────────────────────────────────────

def generate_ai_roadmap(topic, level, goal, hours_per_week=10, weeks=8):
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return _mock_roadmap(topic, level, weeks, hours_per_week)

    prompt = f"""You are an expert learning coach. Create a detailed personalised learning roadmap.

Topic: {topic}
Current Level: {level}
Goal: {goal or 'Become proficient'}
Hours per week: {hours_per_week}
Duration: {weeks} weeks

Return ONLY valid JSON (no markdown fences) with this structure:
{{
  "title": "string",
  "summary": "string",
  "totalWeeks": {weeks},
  "hoursPerWeek": {hours_per_week},
  "weeks": [
    {{
      "week": 1,
      "theme": "string",
      "objectives": ["string","string","string"],
      "topics": ["string","string"],
      "resources": [
        {{"type": "youtube|udemy|coursera|practice|book", "title": "string", "url": "string or null"}}
      ],
      "milestone": "string",
      "estimatedHours": {hours_per_week}
    }}
  ],
  "skills": ["skill1","skill2","skill3","skill4","skill5"],
  "tips": ["tip1","tip2","tip3"]
}}"""

    try:
        r = requests.post("https://api.anthropic.com/v1/messages", headers={
            "Content-Type": "application/json",
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
        }, json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=60)
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        return json.loads(re.sub(r"```json|```", "", text).strip())
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _mock_roadmap(topic, level, weeks, hours_per_week)


def search_microsoft_learn_courses(query: str, limit: int = 12) -> list:
    """Search Microsoft Learn modules and learning paths.
    
    API returns learning modules and paths from Microsoft Learn catalog.
    Fields: title, description, duration, level, url, prerequisites, etc.
    """
    try:
        # Microsoft Learn API endpoint (public, no key needed)
        r = requests.get(
            "https://learn.microsoft.com/api/catalog/",
            params={
                "locale": "en-us",
                "type": "learningPaths,modules",
                "search": query,
            },
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        
        results = []
        items = data.get("items", [])[:limit]
        
        for item in items:
            # Extract relevant fields from the API response
            item_type = item.get("kind", "module")  # "module" or "learningPath"
            title = item.get("title", "")
            url = item.get("url", "")
            description = item.get("description", "")
            duration_minutes = item.get("duration_minutes", 0)
            
            # Format duration
            if duration_minutes:
                hours = duration_minutes // 60
                mins = duration_minutes % 60
                if hours > 0:
                    duration = f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
                else:
                    duration = f"{mins}m"
            else:
                duration = "Self-paced"
            
            # Determine level from metadata
            level_str = item.get("level", "")
            if level_str:
                level = "Beginner" if "beginner" in level_str.lower() else \
                        "Advanced" if "advanced" in level_str.lower() else \
                        "Intermediate" if "intermediate" in level_str.lower() else "All Levels"
            else:
                level = _infer_level(title)
            
            results.append({
                "platform": "microsoft_learn",
                "id": item.get("uid", ""),
                "title": title,
                "org": "Microsoft",
                "thumbnail": item.get("image_url", "https://learn.microsoft.com/favicon.ico"),
                "description": description[:150] + "..." if description and len(description) > 150 else description,
                "rating": "4.7",
                "enrolled": "500K+",
                "duration": duration,
                "level": level,
                "badge": "Learning Path" if item_type == "learningPath" else "Module",
                "url": url,
                "free": True,
                "price": "Free",
                "type": item_type,
            })
        return results
    except Exception as e:
        logger.error(f"Microsoft Learn API error: {e}")
        return _mock_microsoft_learn(query)


def search_all_platforms(query):
    """
    Search across all active platforms for courses.
    
    Supported platforms: YouTube, Udemy, Microsoft Learn
    (Coursera API was removed due to 405 errors)
    
    Args:
        query (str): Search query
    
    Returns:
        dict: Results keyed by platform name, each containing a list of course objects
    """
    results = {"youtube": [], "udemy": [], "microsoft_learn": [], "coursera": [], "query": query}
    for platform, fn in [
        ("youtube",         lambda: search_youtube_courses(query, max_results=6)),
        ("udemy",           lambda: search_udemy_courses(query, page_size=6)),
        ("microsoft_learn", lambda: search_microsoft_learn_courses(query, limit=12)),
        ("coursera",        lambda: search_coursera_courses(query, limit=6)),
    ]:
        try:
            results[platform] = fn()
        except Exception as e:
            logger.error(f"{platform} failed: {e}")
    return results


def search_coursera_courses(query: str, limit: int = 6) -> list:
    """Search Coursera public catalog for courses matching `query`.

    Uses the Coursera public API endpoint defined in settings.COURSERA_API_URL.
    The API supports q=search and query=<text>. This function is defensive and
    returns a small mock list if the real API is unreachable (which has been a
    chronic problem due to 405 errors on Coursera's deprecated backend).
    """
    base = getattr(settings, "COURSERA_API_URL", "https://api.coursera.org/api/courses.v1?limit=20")
    try:
        params = {"q": "search", "query": query, "limit": limit}
        r = requests.get(base, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        # Coursera v1 response typically contains 'elements' with course data
        elements = data.get("elements") or data.get("courses") or []
        results = []
        for el in elements[:limit]:
            # defensive field extraction
            title = el.get("name") or el.get("title") or el.get("fullName") or el.get("slug", "")
            slug = el.get("slug", "")
            course_id = el.get("id") or el.get("courseId") or slug
            description = el.get("description") or el.get("short_description") or ""
            thumbnail = el.get("photoUrl") or el.get("logo") or ""
            url = f"https://www.coursera.org/learn/{slug}" if slug else "https://www.coursera.org"

            results.append({
                "platform": "coursera",
                "id": str(course_id),
                "title": title,
                "thumbnail": thumbnail,
                "description": description[:150] + "..." if description and len(description) > 150 else description,
                "url": url,
                "level": _infer_level(title),
                "free": False,
                "price": "Varies",
            })
        return results
    except Exception as e:
        logger.error(f"Coursera API error: {e}")
        # fall back to a mock so we at least show something in the UI
        return _mock_coursera(query)


# ── Helpers ──────────────────────────────────────────────────────

def _format_number(n):
    """Format large numbers with K and M suffixes."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M+"
    if n >= 1_000:
        return f"{n/1_000:.0f}K+"
    return str(n)

def _parse_duration(iso):
    """Parse ISO 8601 duration format (e.g., PT1H30M) to human-readable format."""
    if not iso:
        return "N/A"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso)
    if not m:
        return "N/A"
    h, mn = int(m.group(1) or 0), int(m.group(2) or 0)
    return f"{h}h {mn}m" if h else f"{mn}m"

def _infer_level(title):
    """Infer course level from title."""
    t = title.lower()
    if any(w in t for w in ["beginner","introduction","basics","zero to"]):
        return "Beginner"
    if any(w in t for w in ["advanced","expert","mastery"]):
        return "Advanced"
    if "intermediate" in t:
        return "Intermediate"
    return "All Levels"


# ── Mock data (used when API keys are empty) ─────────────────────

def _mock_coursera(q):
    """Minimal fake Coursera courses so that the front end has something to
    show even when the real API is disabled or failing.
    """
    return [
        {"platform":"coursera","id":"coursera1","title":f"{q} for Beginners",
         "thumbnail":"https://via.placeholder.com/240x135?text=Coursera",
         "description":"A mock Coursera course to populate the UI",
         "url":"https://www.coursera.org","level":"Beginner","price":"Free"},
        {"platform":"coursera","id":"coursera2","title":f"Advanced {q}",
         "thumbnail":"https://via.placeholder.com/240x135?text=Coursera",
         "description":"Another sample course","url":"https://www.coursera.org",
         "level":"Advanced","price":"Varies"},
    ]

def _mock_youtube(q):
    return [
        {"platform":"youtube","id":"yt1","title":f"{q} Full Course for Beginners","channel":"freeCodeCamp.org",
         "thumbnail":"https://i.ytimg.com/vi/rfscVS0vtbw/hqdefault.jpg","views":"12.3M","duration":"4h 26m",
         "url":"https://www.youtube.com/@freecodecamp","level":"Beginner","free":True,"price":"Free"},
        {"platform":"youtube","id":"yt2","title":f"{q} Tutorial — Project Based Learning","channel":"Traversy Media",
         "thumbnail":"https://i.ytimg.com/vi/ysEN5RaKOlA/hqdefault.jpg","views":"2.1M","duration":"2h 10m",
         "url":"https://www.youtube.com/@TraversyMedia","level":"Intermediate","free":True,"price":"Free"},
        {"platform":"youtube","id":"yt3","title":f"Advanced {q} in 100 Seconds","channel":"Fireship",
         "thumbnail":"https://i.ytimg.com/vi/DHvZLI7Db8E/hqdefault.jpg","views":"890K","duration":"45m",
         "url":"https://www.youtube.com/@Fireship","level":"Advanced","free":True,"price":"Free"},
    ]

def _mock_udemy(q):
    return [
        {"platform":"udemy","id":"u1","title":f"The Complete {q} Bootcamp","instructor":"Angela Yu",
         "thumbnail":"https://img-c.udemyassets.com/course/480x270/1565838_e54e_16.jpg",
         "rating":"4.7","students":"900K+","price":"₹499","level":"Beginner","badge":"Bestseller",
         "url":"https://www.udemy.com","free":False},
        {"platform":"udemy","id":"u2","title":f"{q} — Advanced Masterclass","instructor":"Maximilian Schwarzmüller",
         "thumbnail":"https://img-c.udemyassets.com/course/480x270/1362070_b9a1_2.jpg",
         "rating":"4.6","students":"350K+","price":"₹449","level":"Intermediate","badge":"Top Rated",
         "url":"https://www.udemy.com","free":False},
    ]


def _mock_roadmap(topic, level, weeks, hpw):
    themes = ["Foundations & Setup","Core Concepts","Hands-on Projects",
              "Intermediate Patterns","Advanced Techniques","Real-world Application",
              "Testing & Best Practices","Capstone Project"]
    return {
        "title": f"{topic} {level} Roadmap",
        "summary": f"A structured {weeks}-week path from {level} to confident practitioner in {topic}. Each week builds progressively with resources from YouTube, Udemy, and Coursera.",
        "totalWeeks": weeks, "hoursPerWeek": hpw,
        "skills": [f"{topic} Fundamentals","Problem Solving","Project Building","Debugging","Best Practices"],
        "weeks": [{"week": i+1, "theme": themes[i % len(themes)], "estimatedHours": hpw,
            "objectives": [f"Understand {topic} core concepts for week {i+1}","Complete all exercises","Build a mini-project"],
            "topics": [f"{topic} week {i+1}","Best practices"],
            "resources": [
                {"type":"youtube",  "title":f"{topic} Week {i+1} Tutorial — freeCodeCamp","url":"https://www.youtube.com/@freecodecamp"},
                {"type":"udemy",    "title":f"Complete {topic} Bootcamp","url":"https://udemy.com"},
                {"type":"practice", "title":f"Build a {topic} mini-project","url":None},
            ],
            "milestone": f"Complete week {i+1} project and push to GitHub",
        } for i in range(min(weeks, 8))],
        "tips": ["Code every day — even 30 minutes counts","Build real projects not just tutorials","Join Discord communities and ask questions"],
    }

def _mock_microsoft_learn(q):
    return [
        {"platform":"microsoft_learn","id":"ml1","title":f"{q} Fundamentals Learning Path","org":"Microsoft",
         "thumbnail":"https://learn.microsoft.com/favicon.ico","rating":"4.7","enrolled":"500K+","duration":"4h 30m",
         "level":"Beginner","badge":"Learning Path","url":"https://learn.microsoft.com","free":True,"price":"Free","type":"learningPath"},
        {"platform":"microsoft_learn","id":"ml2","title":f"Introduction to {q}","org":"Microsoft",
         "thumbnail":"https://learn.microsoft.com/favicon.ico","rating":"4.7","enrolled":"300K+","duration":"2h 15m",
         "level":"Beginner","badge":"Module","url":"https://learn.microsoft.com","free":True,"price":"Free","type":"module"},
    ]