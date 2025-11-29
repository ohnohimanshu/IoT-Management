from django import forms
from .models import Device

class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ['device_name', 'device_id','email', 'high_temp_threshold' ]





class GlobalIntervalForm(forms.Form):
    email_interval = forms.IntegerField(
        min_value=1,
        label="Email Alert Interval (minutes)",
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter interval in minutes'
        })
    )