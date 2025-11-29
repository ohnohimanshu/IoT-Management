import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esp_project.settings')

app = Celery('esp_project')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure Celery Beat schedule
app.conf.beat_schedule = {
    'send-daily-summaries': {
        'task': 'mailer.tasks.send_daily_summaries',
        'schedule': crontab(hour=9, minute=0),  # Run at 9 AM every day
    },
    'reset-status-change-count': {
        'task': 'devices.tasks.reset_status_change_count',
        'schedule': crontab(hour=9, minute=0),  # Run at 9 AM every day
    },
    'check-firmware-updates': {
        'task': 'ota_update.tasks.check_for_firmware_updates',
        'schedule': crontab(hour=2, minute=0),  # Run at 2 AM every day
    },
    'auto-update-devices': {
        'task': 'ota_update.tasks.auto_update_devices',
        'schedule': crontab(hour=3, minute=0),  # Run at 3 AM every day
    },
    'cleanup-old-ota-updates': {
        'task': 'ota_update.tasks.cleanup_old_ota_updates',
        'schedule': crontab(hour=1, minute=0, day_of_week=0),  # Run weekly on Sunday at 1 AM
    },
    'timeout-stalled-updates': {
        'task': 'ota_update.tasks.timeout_stalled_updates',
        'schedule': crontab(minute='*/15'),  # Run every 15 minutes
    },
}

# Configure Celery to use Redis as broker and result backend
app.conf.broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
app.conf.result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

# Configure Celery task settings
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'
app.conf.timezone = settings.TIME_ZONE
app.conf.enable_utc = True
app.conf.task_track_started = True
app.conf.task_time_limit = 30 * 60  # 30 minutes hard limit
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes soft limit
