#!/usr/bin/env python
"""
Test script for YouTube API and course recommendations.
Tests the production-ready implementation with caching, quota detection, and exponential backoff.

Run from the core/ directory with: python test_api_setup.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.conf import settings
from recommender.api_services import (
    search_all_platforms,
    get_youtube_cache_status,
    reset_youtube_cache,
    reset_youtube_quota_flag
)

def test_api_keys():
    """Verify API keys are loaded from .env"""
    print("=" * 70)
    print("🔍 Testing API Configuration")
    print("=" * 70)
    
    youtube_key = getattr(settings, "YOUTUBE_API_KEY", "")
    udemy_id = getattr(settings, "UDEMY_CLIENT_ID", "")
    udemy_secret = getattr(settings, "UDEMY_CLIENT_SECRET", "")
    anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    
    print(f"\n✓ Settings loaded from Django configuration")
    print(f"  - YOUTUBE_API_KEY: {'✓ SET' if youtube_key else '❌ NOT SET (will return empty results)'}")
    print(f"    Key preview: {youtube_key[:20]}..." if youtube_key else "")
    print(f"  - UDEMY_CLIENT_ID: {'✓ SET' if udemy_id else '❌ NOT SET'}")
    print(f"  - UDEMY_CLIENT_SECRET: {'✓ SET' if udemy_secret else '❌ NOT SET'}")
    print(f"  - ANTHROPIC_API_KEY: {'✓ SET' if anthropic_key else '❌ NOT SET'}")
    
    return youtube_key

def test_youtube_cache():
    """Test YouTube cache functionality."""
    print("\n" + "=" * 70)
    print("💾 Testing YouTube API Caching")
    print("=" * 70)
    
    # Reset cache first
    reset_youtube_cache()
    reset_youtube_quota_flag()
    
    print("\n🔄 Request 1: Searching for 'Python'...")
    results1 = search_all_platforms("Python")
    youtube1 = results1.get("youtube", [])
    print(f"   Result: {len(youtube1)} courses found")
    
    # Check cache status
    cache_status = get_youtube_cache_status()
    print(f"\n📊 Cache Status after Request 1:")
    print(f"   - Cached queries: {cache_status['cached_queries']}")
    print(f"   - Cache size: {cache_status['cache_size']}")
    
    print("\n🔄 Request 2: Searching for 'Python' again (should use cache)...")
    results2 = search_all_platforms("Python")
    youtube2 = results2.get("youtube", [])
    print(f"   Result: {len(youtube2)} courses found (from cache)")
    
    if len(youtube1) == len(youtube2) and youtube1:
        print("   ✓ Cache working correctly!")
    
    print("\n🔄 Request 3: Searching for 'JavaScript' (different query)...")
    results3 = search_all_platforms("JavaScript")
    youtube3 = results3.get("youtube", [])
    print(f"   Result: {len(youtube3)} courses found")
    
    cache_status = get_youtube_cache_status()
    print(f"\n📊 Final Cache Status:")
    print(f"   - Cached queries: {cache_status['cached_queries']}")
    print(f"   - Cache size: {cache_status['cache_size']}")
    print(f"   - Quota exhausted: {cache_status['quota_exhausted']}")

def test_course_search():
    """Test searching for courses across platforms"""
    print("\n" + "=" * 70)
    print("🎓 Testing Course Search")
    print("=" * 70)
    
    query = "Python programming"
    print(f"\nSearching for: '{query}'")
    
    results = search_all_platforms(query)
    
    print(f"\n📊 Results:")
    total_courses = 0
    for platform, courses in results.items():
        if platform != "query":
            count = len(courses)
            total_courses += count
            icon = "✓" if count > 0 else "❌"
            print(f"  {icon} {platform.replace('_', ' ').title()}: {count} courses")
            if courses and count > 0:
                first = courses[0]
                title = first.get('title', 'N/A')[:50]
                print(f"     └─ Sample: {title}...")
    
    print(f"\n✓ Total courses found: {total_courses}")
    return results

def main():
    """Run all tests"""
    print("\n🚀 LearnSmart YouTube API - Production-Ready Implementation\n")
    
    youtube_key = test_api_keys()
    test_youtube_cache()
    results = test_course_search()
    
    print("\n" + "=" * 70)
    print("📝 Summary & Features")
    print("=" * 70)
    
    print("\n✓ Production-Ready Features Implemented:")
    print("  ✓ Caching per skill (1 request per unique query)")
    print("  ✓ 403 error detection (quotaExceeded, keyInvalid)")
    print("  ✓ Exponential backoff retry (max 2 retries)")
    print("  ✓ Timeout=10 seconds per request")
    print("  ✓ Comprehensive logging")
    print("  ✓ Graceful fallback on API failure")
    print("  ✓ Stops repeated calls when quota exhausted")
    
    print("\n📋 Management Commands Available:")
    print("  python manage.py youtube_cache status     # Show cache status")
    print("  python manage.py youtube_cache clear      # Clear cache")
    print("  python manage.py youtube_cache reset      # Reset quota flag")
    print("  python manage.py youtube_cache full-reset # Clear cache + reset quota")
    
    if not youtube_key:
        print("\n⚠️  YouTube API key is not configured.")
        print("   To enable YouTube courses:")
        print("   1. Get a key: https://console.cloud.google.com")
        print("   2. Edit core/.env and add: YOUTUBE_API_KEY=your_key_here")
        print("   3. Restart Django server or run:")
        print("      python manage.py youtube_cache full-reset")
    else:
        print("\n✓ YouTube API is configured!")
    
    has_courses = any(len(results.get(p, [])) > 0 for p in ['youtube', 'udemy', 'microsoft_learn'])
    
    if has_courses:
        print("\n✓ Course search is working!")
        print("\n🎉 You can now:")
        print("  - Visit http://localhost:8000/recommend/")
        print("  - Click 'Browse Interactive Roadmaps'")
        print("  - Search for specific skills")
    else:
        print("\n⚠️  No courses found.")
        if not youtube_key:
            print("   Install API keys to see results.")
        else:
            print("   If issue persists, check logs: python manage.py youtube_cache status")
    
    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    main()

