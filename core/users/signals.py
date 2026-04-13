from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CustomUser
from .models import UserProfile


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(
            user=instance,
            name=instance.username,
            email=instance.email or "",
        )


@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    try:
        profile = instance.userprofile
        profile.email = instance.email or profile.email
        profile.name = instance.username or profile.name
        profile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance, name=instance.username, email=instance.email or "")