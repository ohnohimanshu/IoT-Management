import logging
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

def format_timestamp(dt):
    """
    Format a datetime object to a human-readable string in local timezone
    """
    if not dt:
        return 'Never'
    return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')

def validate_email_settings(settings):
    """
    Validate that all required email settings are configured
    """
    required = ['EMAIL_HOST', 'EMAIL_PORT', 'DEFAULT_FROM_EMAIL', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD']
    
    # Check if all required settings exist and have non-empty values
    for key in required:
        value = getattr(settings, key, None)
        if not value:  # This will catch None, empty string, 0, etc.
            logger.error(f"❌ Missing or empty email setting: {key}")
            return False
    
    # All settings are present and have values
    logger.info("✅ Email settings validated successfully")
    return True