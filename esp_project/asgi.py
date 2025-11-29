"""
ASGI config for esp_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
import logging
import threading
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from devices.routing import websocket_urlpatterns
from devices.services import execute_scheduled_commands

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esp_project.settings')

# Get the ASGI application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})

# Start background tasks
def start_background_tasks():
    try:
        from mailer.views import start_background_tasks
        from mailer.device_monitor import monitor_device_status
        from mailer.temperature_monitor import monitor_temperature
        from mailer.lora_monitor import start_monitor
        from devices.services import execute_scheduled_commands
        
        logger.info("📡 Starting background threads from asgi.py")
        print("📡 Starting background threads from asgi.py")
        
        # Start scheduled commands runner
        scheduled_commands_thread = threading.Thread(
            target=lambda: execute_scheduled_commands_loop(),
            daemon=True,
            name='ScheduledCommandsRunner'
        )
        scheduled_commands_thread.start()
        logger.info("⚡ Scheduled Commands Runner started")
        print("⚡ Background Task Running: Scheduled Commands Runner")
        
        # Start device status monitoring
        status_thread = threading.Thread(
            target=monitor_device_status,
            daemon=True,
            name='DeviceStatusMonitor'
        )
        status_thread.start()
        logger.info("🚀 Device Status Monitor started")
        print("🚀 Background Task Running: Device Status Monitor")
        
        # Start temperature monitoring
        temp_thread = threading.Thread(
            target=monitor_temperature,
            daemon=True,
            name='TemperatureMonitor'
        )
        temp_thread.start()
        logger.info("🌡️ Temperature Monitor started")
        print("🌡️ Background Task Running: Temperature Monitor")
        
        # Start LoRa device monitoring
        lora_thread = start_monitor()
        logger.info("📡 LoRa Device Monitor started")
        print("📡 Background Task Running: LoRa Device Monitor")
        
        logger.info("✅ All background tasks started successfully")
        print("✅ All background tasks started successfully")
        
    except Exception as e:
        logger.error(f"❌ Error starting background tasks: {str(e)}")
        print(f"❌ Error starting background tasks: {str(e)}")

def execute_scheduled_commands_loop():
    import time
    logger.info("Starting scheduled commands loop")
    while True:
        try:
            logger.info("Checking for scheduled commands...")
            execute_scheduled_commands()
            logger.info("Scheduled commands check completed")
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in scheduled commands runner: {str(e)}")
            time.sleep(60)  # Wait a minute before retrying

# Start the background tasks
start_background_tasks()
