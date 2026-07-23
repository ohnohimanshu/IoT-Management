from django import forms
from .models import EmailRecipient, MailerConfiguration

class EmailRecipientForm(forms.ModelForm):
    class Meta:
        model = EmailRecipient
        fields = ['email']  # Don't include 'added_at' here


class MailerConfigurationForm(forms.ModelForm):
    # Unit choices for each duration field
    UNIT_CHOICES = [
        ('seconds', 'Seconds'),
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
    ]
    
    # Device monitor fields with units
    inactivity_threshold_value = forms.IntegerField(
        label='Inactivity Threshold',
        help_text='Duration before device is considered inactive',
        min_value=1
    )
    inactivity_threshold_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    email_rate_limit_value = forms.IntegerField(
        label='Email Rate Limit',
        help_text='Minimum duration between emails for the same device',
        min_value=1
    )
    email_rate_limit_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    status_confirmation_wait_value = forms.IntegerField(
        label='Status Confirmation Wait',
        help_text='Wait duration to confirm status change before sending email',
        min_value=1
    )
    status_confirmation_wait_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    monitor_interval_value = forms.IntegerField(
        label='Monitor Interval',
        help_text='How often to check all devices',
        min_value=1
    )
    monitor_interval_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    
    # Temperature monitor fields with units
    temperature_check_interval_value = forms.IntegerField(
        label='Temperature Check Interval',
        help_text='How often to check device temperatures',
        min_value=1
    )
    temperature_check_interval_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    temperature_alert_interval_value = forms.IntegerField(
        label='Temperature Alert Interval',
        help_text='How often to send repeat temperature alerts',
        min_value=1
    )
    temperature_alert_interval_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    
    # LoRa monitor fields with units
    lora_check_interval_value = forms.IntegerField(
        label='LoRa Check Interval',
        help_text='How often to check LoRa devices',
        min_value=1
    )
    lora_check_interval_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    lora_notification_interval_value = forms.IntegerField(
        label='LoRa Notification Interval',
        help_text='How often to send repeat LoRa notifications',
        min_value=1
    )
    lora_notification_interval_unit = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial='seconds'
    )
    
    class Meta:
        model = MailerConfiguration
        fields = []  # All fields are custom defined above
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if name.endswith('_unit'):
                field.widget.attrs.update({
                    'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary focus:ring-primary'
                })
            else:
                field.widget.attrs.update({
                    'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary focus:ring-primary',
                    'min': '1'
                })
        
        # Convert stored seconds to appropriate value and unit for initial form data
        if self.instance:
            # Device monitor
            self._set_initial_value_and_unit(
                'inactivity_threshold',
                self.instance.inactivity_threshold
            )
            self._set_initial_value_and_unit(
                'email_rate_limit',
                self.instance.email_rate_limit
            )
            self._set_initial_value_and_unit(
                'status_confirmation_wait',
                self.instance.status_confirmation_wait
            )
            self._set_initial_value_and_unit(
                'monitor_interval',
                self.instance.monitor_interval
            )
            
            # Temperature monitor
            self._set_initial_value_and_unit(
                'temperature_check_interval',
                self.instance.temperature_check_interval
            )
            self._set_initial_value_and_unit(
                'temperature_alert_interval',
                self.instance.temperature_alert_interval
            )
            
            # LoRa monitor
            self._set_initial_value_and_unit(
                'lora_check_interval',
                self.instance.lora_check_interval
            )
            self._set_initial_value_and_unit(
                'lora_notification_interval',
                self.instance.lora_notification_interval
            )
    
    def _set_initial_value_and_unit(self, field_base_name, total_seconds):
        """Helper method to set initial value and unit based on total seconds"""
        if total_seconds % 3600 == 0:
            value = total_seconds // 3600
            unit = 'hours'
        elif total_seconds % 60 == 0:
            value = total_seconds // 60
            unit = 'minutes'
        else:
            value = total_seconds
            unit = 'seconds'
        
        self.fields[f'{field_base_name}_value'].initial = value
        self.fields[f'{field_base_name}_unit'].initial = unit
    
    def _get_total_seconds(self, field_base_name):
        """Helper method to convert value+unit to total seconds"""
        value = self.cleaned_data[f'{field_base_name}_value']
        unit = self.cleaned_data[f'{field_base_name}_unit']
        
        if unit == 'hours':
            return value * 3600
        elif unit == 'minutes':
            return value * 60
        else:  # seconds
            return value
    
    def save(self, commit=True):
        """Save the model instance with all fields converted to seconds"""
        instance = super().save(commit=False)
        
        # Device monitor
        instance.inactivity_threshold = self._get_total_seconds('inactivity_threshold')
        instance.email_rate_limit = self._get_total_seconds('email_rate_limit')
        instance.status_confirmation_wait = self._get_total_seconds('status_confirmation_wait')
        instance.monitor_interval = self._get_total_seconds('monitor_interval')
        
        # Temperature monitor
        instance.temperature_check_interval = self._get_total_seconds('temperature_check_interval')
        instance.temperature_alert_interval = self._get_total_seconds('temperature_alert_interval')
        
        # LoRa monitor
        instance.lora_check_interval = self._get_total_seconds('lora_check_interval')
        instance.lora_notification_interval = self._get_total_seconds('lora_notification_interval')
        
        if commit:
            instance.save()
        
        return instance
