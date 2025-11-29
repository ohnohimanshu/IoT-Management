from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('device-administrator', 'Device Administrator'),
        ('user', 'User'),
    )
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    email_notifications = models.CharField(max_length=20, choices=[
        ('all', 'All Alerts'),
        ('important', 'Important Only'),
        ('none', 'None')
    ], default='all')
    update_interval = models.IntegerField(default=15)  # in minutes

    def __str__(self):
        return self.username
