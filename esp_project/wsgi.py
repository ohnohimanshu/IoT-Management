"""
WSGI config for esp_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os
import logging
import threading
from django.core.wsgi import get_wsgi_application

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esp_project.settings')

# Get the WSGI application
application = get_wsgi_application()

def execute_scheduled_commands_loop():
    import time
    logger.info("Starting scheduled commands loop")
    while True:
        try:
            logger.info("Checking for scheduled commands...")
            from devices.services import execute_scheduled_commands
            execute_scheduled_commands()
            logger.info("Scheduled commands check completed")
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in scheduled commands runner: {str(e)}")
            time.sleep(60)  # Wait a minute before retrying

def execute_daily_summary_scheduler():
    """
    Runs daily summary email task at 11:00 AM IST (or configured time)
    """
    import time
    from datetime import datetime
    from django.utils import timezone
    
    logger.info("🗓️ Starting daily summary scheduler")
    
    last_run_date = None
    
    while True:
        try:
            now = timezone.now()
            current_hour = now.hour
            current_minute = now.minute
            current_date = now.date()
            
            # Check if it's 11:00 AM (hour=11, minute between 0-1 to run within first minute)
            if current_hour == 9 and current_minute == 0 and current_date != last_run_date:
                logger.info("⏰ Daily summary time reached! Executing send_daily_summaries task...")
                print("⏰ Executing daily summary email task at 11:00 AM")
                
                try:
                    from mailer.tasks import send_daily_summaries
                    result = send_daily_summaries.apply_async()
                    logger.info(f"📧 Daily summary task queued with ID: {result.id}")
                    print(f"📧 Daily summary task queued with ID: {result.id}")
                    last_run_date = current_date
                except Exception as task_error:
                    logger.error(f"❌ Error executing daily summary task: {str(task_error)}")
                    import traceback
                    traceback.print_exc()
            
            # Sleep for 30 seconds before checking again
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in daily summary scheduler: {str(e)}")
            import traceback
            traceback.print_exc()
            time.sleep(60)  # Wait a minute before retrying

# Start background tasks after Django is fully loaded
def start_background_tasks():
    try:
        from mailer.views import start_background_tasks
        from mailer.device_monitor import monitor_device_status
        from mailer.temperature_monitor import monitor_temperature
        from mailer.lora_monitor import start_monitor
        
        logger.info("📡 Starting background threads from wsgi.py")
        print("📡 Starting background threads from wsgi.py")
        
        # Start scheduled commands runner
        scheduled_commands_thread = threading.Thread(
            target=execute_scheduled_commands_loop,
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
        
        # Start daily summary scheduler
        summary_thread = threading.Thread(
            target=execute_daily_summary_scheduler,
            daemon=True,
            name='DailySummaryScheduler'
        )
        summary_thread.start()
        logger.info("🗓️ Daily Summary Scheduler started")
        print("🗓️ Background Task Running: Daily Summary Scheduler")
        
        logger.info("✅ All background tasks started successfully")
        print("✅ All background tasks started successfully")
        
    except Exception as e:
        logger.error(f"❌ Error starting background tasks: {str(e)}")
        print(f"❌ Error starting background tasks: {str(e)}")

# Start the background tasks
start_background_tasks()
