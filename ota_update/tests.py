from django.test import TestCase
from django.contrib.auth import get_user_model
from devices.models import Device
from .models import FirmwareVersion, OTAUpdate, DeviceFirmwareInfo

User = get_user_model()


class OTAUpdateTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='device-administrator'
        )
        
        self.device = Device.objects.create(
            device_name='Test ESP32',
            device_id='test_esp32_001',
            device_type='esp32',
            user=self.user,
            added_by=self.user,
            email='device@example.com'
        )
        
        self.firmware = FirmwareVersion.objects.create(
            name='Test Firmware v1.0',
            version_number='1.0.0',
            device_type='esp32',
            created_by=self.user,
            description='Test firmware version'
        )

    def test_firmware_version_creation(self):
        self.assertEqual(self.firmware.name, 'Test Firmware v1.0')
        self.assertEqual(self.firmware.device_type, 'esp32')
        self.assertTrue(self.firmware.is_active)

    def test_ota_update_creation(self):
        ota_update = OTAUpdate.objects.create(
            device=self.device,
            firmware_version=self.firmware,
            initiated_by=self.user
        )
        
        self.assertEqual(ota_update.status, 'pending')
        self.assertEqual(ota_update.progress_percentage, 0)
        self.assertEqual(ota_update.device, self.device)

    def test_device_firmware_info_creation(self):
        firmware_info = DeviceFirmwareInfo.objects.create(
            device=self.device,
            current_version='0.9.0'
        )
        
        self.assertEqual(firmware_info.current_version, '0.9.0')
        self.assertFalse(firmware_info.update_available)
        self.assertFalse(firmware_info.auto_update_enabled)

    def test_ota_update_progress_tracking(self):
        ota_update = OTAUpdate.objects.create(
            device=self.device,
            firmware_version=self.firmware,
            initiated_by=self.user
        )
        
        # Test progress update
        ota_update.update_progress(50, "Downloading firmware")
        self.assertEqual(ota_update.progress_percentage, 50)
        self.assertTrue(len(ota_update.update_log) > 0)
        
        # Test completion
        ota_update.mark_completed()
        self.assertEqual(ota_update.status, 'completed')
        self.assertEqual(ota_update.progress_percentage, 100)

    def test_ota_update_failure_handling(self):
        ota_update = OTAUpdate.objects.create(
            device=self.device,
            firmware_version=self.firmware,
            initiated_by=self.user
        )
        
        error_message = "Network connection failed"
        ota_update.mark_failed(error_message)
        
        self.assertEqual(ota_update.status, 'failed')
        self.assertEqual(ota_update.error_message, error_message)
        self.assertIsNotNone(ota_update.completed_at)