from django.db import models
from django.contrib.auth.models import AbstractUser
from bson import ObjectId


class CustomUser(AbstractUser):
    id = models.CharField(max_length=24, primary_key=True, default=lambda: str(ObjectId()), editable=False)

    class Meta:
        db_table = 'auth_user'

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = str(ObjectId())
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='userprofile')
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    interests = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.name:
            return self.name
        return self.user.username

