from django import forms
from .models import FirmwareVersion


class FirmwareUploadForm(forms.ModelForm):
    class Meta:
        model = FirmwareVersion
        fields = ['name', 'description', 'firmware_file', 'device_type', 'version_number']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ESP32 Sensor Firmware v1.2.3'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the changes in this firmware version...'
            }),
            'firmware_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.bin'
            }),
            'device_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'version_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 1.2.3'
            })
        }

    def clean_firmware_file(self):
        firmware_file = self.cleaned_data.get('firmware_file')
        
        if firmware_file:
            # Check file extension
            if not firmware_file.name.lower().endswith('.bin'):
                raise forms.ValidationError('Only .bin files are allowed')
            
            # Check file size (max 4MB for ESP devices)
            if firmware_file.size > 4 * 1024 * 1024:
                raise forms.ValidationError('Firmware file size cannot exceed 4MB')
        
        return firmware_file

    def clean_version_number(self):
        version_number = self.cleaned_data.get('version_number')
        device_type = self.cleaned_data.get('device_type')
        
        if version_number and device_type:
            # Check if version already exists for this device type
            existing = FirmwareVersion.objects.filter(
                version_number=version_number,
                device_type=device_type
            )
            
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError(
                    f'Version {version_number} already exists for {device_type} devices'
                )
        
        return version_number