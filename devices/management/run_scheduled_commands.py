from django.core.management.base import BaseCommand
from devices.services import execute_scheduled_commands
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs scheduled commands for devices'

    def handle(self, *args, **options):
        self.stdout.write('Starting scheduled commands runner...')
        
        while True:
            try:
                execute_scheduled_commands()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduled commands runner: {str(e)}")
                time.sleep(60)  # Wait a minute before retrying 