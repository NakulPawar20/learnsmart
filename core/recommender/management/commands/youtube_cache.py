"""
Django management command to manage YouTube API cache and quota state.

Usage:
    python manage.py youtube_cache status      # Show cache status
    python manage.py youtube_cache clear       # Clear all cached results
    python manage.py youtube_cache reset       # Reset quota exhausted flag
    python manage.py youtube_cache full-reset  # Clear cache AND reset quota flag
"""

from django.core.management.base import BaseCommand, CommandError
from recommender.api_services import (
    reset_youtube_cache,
    reset_youtube_quota_flag,
    get_youtube_cache_status,
    _youtube_cache,
    _youtube_quota_exhausted
)


class Command(BaseCommand):
    help = "Manage YouTube API cache and quota state"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            type=str,
            choices=["status", "clear", "reset", "full-reset"],
            help="Action to perform: status|clear|reset|full-reset"
        )

    def handle(self, *args, **options):
        action = options["action"]

        if action == "status":
            self.show_status()
        elif action == "clear":
            self.clear_cache()
        elif action == "reset":
            self.reset_quota()
        elif action == "full-reset":
            self.full_reset()

    def show_status(self):
        """Display cache and quota status."""
        status = get_youtube_cache_status()
        
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("YouTube API Cache Status"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        
        self.stdout.write(f"\n📊 Cache Size: {status['cache_size']} queries")
        
        if status['cached_queries']:
            self.stdout.write(self.style.SUCCESS("\n✓ Cached Queries:"))
            for query in status['cached_queries']:
                self.stdout.write(f"  - {query}")
        else:
            self.stdout.write(self.style.WARNING("\n  (empty)"))
        
        quota_status = (
            self.style.ERROR("❌ EXHAUSTED") if status['quota_exhausted']
            else self.style.SUCCESS("✓ AVAILABLE")
        )
        self.stdout.write(f"\n🔒 Quota Status: {quota_status}")
        self.stdout.write("\n" + "=" * 60 + "\n")

    def clear_cache(self):
        """Clear all cached results."""
        reset_youtube_cache()
        self.stdout.write(
            self.style.SUCCESS(
                "✓ YouTube API cache cleared.\n"
                "  Next requests will fetch fresh data from YouTube."
            )
        )

    def reset_quota(self):
        """Reset quota exhausted flag."""
        reset_youtube_quota_flag()
        self.stdout.write(
            self.style.SUCCESS(
                "✓ YouTube API quota flag reset.\n"
                "  API requests will resume (if quota is actually available)."
            )
        )

    def full_reset(self):
        """Clear cache and reset quota flag."""
        reset_youtube_cache()
        reset_youtube_quota_flag()
        self.stdout.write(
            self.style.SUCCESS(
                "✓ YouTube API cache cleared AND quota flag reset.\n"
                "  Fresh API requests will begin on next call."
            )
        )
