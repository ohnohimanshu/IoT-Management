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

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != 'admin':
            self.role = 'admin'
        elif not self.is_superuser and not self.role:
            self.role = 'user'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
