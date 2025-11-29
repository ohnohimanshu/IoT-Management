from django.urls import path
from . import views

urlpatterns = [
    path('email-recipients/', views.email_recipient_list, name='email_recipient_list'),
    path('delete-email-recipient/<int:recipient_id>/', views.delete_email_recipient, name='delete_email_recipient'),
    path('send-device-status-email/<int:device_id>/', views.send_device_status_email, name='send_device_status_email'),
    path('device-charts/<int:device_id>/', views.device_charts, name='device_charts'),
    path('daily-summary/<int:device_id>/', views.daily_summary, name='daily_summary'),
    path('alerts/', views.get_user_alerts, name='get_user_alerts'),
    path('alerts/unread-count/', views.get_unread_alerts_count, name='get_unread_alerts_count'),
    path('alerts/<int:alert_id>/mark-read/', views.mark_alert_read, name='mark_alert_read'),
    path('alerts/mark-all-read/', views.mark_all_alerts_read, name='mark_all_alerts_read'),
    path('send-device-status-email-to-recipient/', views.send_device_status_email_to_recipient, name='send_device_status_email_to_recipient'),
]

