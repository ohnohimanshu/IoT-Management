from django.core.management.base import BaseCommand
from django.utils import timezone
from ota_update.services import OTAUpdateService
from ota_update.models import DeviceFirmwareInfo, FirmwareVersion
from devices.models import Device


class Command(BaseCommand):
    help = 'Check for available OTA updates for all ESP devices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-id',
            type=str,
            help='Check updates for specific device ID',
        )
        parser.add_argument(
            '--auto-update',
            action='store_true',
            help='Automatically start updates for devices with auto-update enabled',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )

    def handle(self, *args, **options):
        service = OTAUpdateService()
        
        # Filter devices
        if options['device_id']:
            devices = Device.objects.filter(
                device_id=options['device_id'],
                device_type__in=['esp', 'esp32', 'esp8266']
            )
            if not devices.exists():
                self.stdout.write(
                    self.style.ERROR(f'Device {options["device_id"]} not found')
                )
                return
        else:
            devices = Device.objects.filter(device_type__in=['esp', 'esp32', 'esp8266'])

        self.stdout.write(f'Checking {devices.count()} ESP devices for updates...')
        
        updates_available = 0
        updates_started = 0
        
        for device in devices:
            # Get or create firmware info
            firmware_info, created = DeviceFirmwareInfo.objects.get_or_create(
                device=device
            )
            
            if created:
                self.stdout.write(f'Created firmware info for {device.device_name}')
            
            # Check for updates
            has_update = firmware_info.check_for_updates()
            
            if has_update:
                updates_available += 1
                available_version = firmware_info.available_version
                
                self.stdout.write(
                    self.style.WARNING(
                        f'Update available for {device.device_name}: '
                        f'{firmware_info.current_version or "Unknown"} -> '
                        f'{available_version.version_number}'
                    )
                )
                
                # Auto-update if enabled and requested
                if options['auto_update'] and firmware_info.auto_update_enabled:
                    if device.device_status != 'online':
                        self.stdout.write(
                            self.style.ERROR(
                                f'Skipping {device.device_name}: device is offline'
                            )
                        )
                        continue
                    
                    if options['dry_run']:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'[DRY RUN] Would start update for {device.device_name}'
                            )
                        )
                        continue
                    
                    # Check for existing active updates
                    from ota_update.models import OTAUpdate
                    active_update = OTAUpdate.objects.filter(
                        device=device,
                        status__in=['pending', 'in_progress']
                    ).exists()
                    
                    if active_update:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Skipping {device.device_name}: update already in progress'
                            )
                        )
                        continue
                    
                    # Create and start update
                    ota_update = OTAUpdate.objects.create(
                        device=device,
                        firmware_version=available_version,
                        initiated_by=device.added_by,
                        previous_version=firmware_info.current_version
                    )
                    
                    success = service.start_ota_update(ota_update)
                    if success:
                        updates_started += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Started OTA update for {device.device_name}'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Failed to start OTA update for {device.device_name}'
                            )
                        )
            else:
                self.stdout.write(f'{device.device_name}: Up to date')
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'Devices checked: {devices.count()}')
        self.stdout.write(f'Updates available: {updates_available}')
        
        if options['auto_update']:
            if options['dry_run']:
                self.stdout.write(f'Updates that would be started: {updates_started}')
            else:
                self.stdout.write(f'Updates started: {updates_started}')
        
        # Show firmware versions summary
        self.stdout.write('\nAvailable firmware versions:')
        for device_type in ['esp32', 'esp8266', 'esp']:
            versions = FirmwareVersion.objects.filter(
                device_type=device_type,
                is_active=True
            ).order_by('-created_at')[:3]  # Show latest 3 versions
            
            if versions.exists():
                self.stdout.write(f'  {device_type.upper()}:')
                for version in versions:
                    self.stdout.write(f'    - {version.version_number} ({version.name})')
        
        self.stdout.write(self.style.SUCCESS('\nOTA update check completed!'))