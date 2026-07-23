from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mailer', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MailerConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inactivity_threshold', models.IntegerField(default=30, help_text='Seconds before device is considered inactive')),
                ('email_rate_limit', models.IntegerField(default=60, help_text='Minimum seconds between emails for same device')),
                ('status_confirmation_wait', models.IntegerField(default=90, help_text='Wait seconds to confirm status change before sending email')),
                ('monitor_interval', models.IntegerField(default=30, help_text='How often to run the monitoring loop (check all devices)')),
                ('temperature_check_interval', models.IntegerField(default=300, help_text='Interval to check device temperatures (seconds)')),
                ('temperature_alert_interval', models.IntegerField(default=300, help_text='Interval to send repeat temperature alerts (seconds)')),
                ('lora_check_interval', models.IntegerField(default=30, help_text='LoRa device check interval (seconds)')),
                ('lora_notification_interval', models.IntegerField(default=300, help_text='LoRa device notification interval (seconds)')),
            ],
            options={
                'db_table': 'mailer_configuration',
            },
        ),
    ]
