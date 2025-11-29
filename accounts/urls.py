from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('', views.home, name='home'),
    path('user/<int:user_id>/', views.view_user_devices, name='view_user_devices'),
    path('logout/', views.logout_view, name='logout'),
    path('user-dashboard/', views.user_dashboard, name='user_dashboard'),
    path('update-user-settings/', views.update_user_settings, name='update_user_settings'),
    path('update-system-settings/', views.update_system_settings, name='update_system_settings'),
    path('<str:device_id>/config/', views.device_config, name='device_config')
]
