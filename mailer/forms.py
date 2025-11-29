from django import forms
from .models import EmailRecipient

class EmailRecipientForm(forms.ModelForm):
    class Meta:
        model = EmailRecipient
        fields = ['email']  # Don't include 'added_at' here
