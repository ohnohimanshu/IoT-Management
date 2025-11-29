from celery import shared_task
from .models import Device

@shared_task
def reset_status_change_count():
    Device.objects.all().update(status_change_count=0) 