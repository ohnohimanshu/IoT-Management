from django.apps import AppConfig
import logging
import threading
import atexit
import sys

logger = logging.getLogger(__name__)

class MailerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mailer'
    
    def ready(self):
        # Only start threads in web server contexts, not during management commands
        # This prevents threads from starting during migrations, collectstatic, etc.
        # Check for common server running commands
        is_server_running = any(cmd in sys.argv for cmd in ['runserver', 'uwsgi', 'gunicorn']) or \
                           'wsgi.py' in sys.argv or 'asgi.py' in sys.argv
        
        # Skip thread creation if not running the server
        if not is_server_running:
            return
            
        # Import here to avoid circular imports
        from .views import start_background_tasks, stop_background_tasks
        from .lora_monitor import start_lora_monitor
        
        logger.info("🔧 Starting background tasks")
        print("🔧 Starting background tasks")
        
        # Start all background tasks
        start_background_tasks()
        
        # Start LoRa monitor
        logger.info("🔧 Starting LoRa device monitor")
        print("🔧 Starting LoRa device monitor")
        lora_monitor_thread = start_lora_monitor()
        
        # Register cleanup function to handle graceful shutdown
        atexit.register(stop_background_tasks)