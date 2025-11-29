from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from .models import CustomUser
from devices.models import Device
from django.http import JsonResponse, HttpResponseForbidden
from mailer.models import EmailRecipient
from mailer.forms import EmailRecipientForm

def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        # Check for duplicate username or email
        if CustomUser.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already exists'}, status=400)
        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists'}, status=400)

        # Create the user
        user = CustomUser.objects.create_user(username=username, email=email, password=password, role=role)
        login(request, user)

        # Redirect based on the role
        redirect_url = redirect_to_dashboard(user).url
        return JsonResponse({'redirect_url': redirect_url})

    return render(request, 'signup.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Authenticate the user
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Determine dashboard redirection
            redirect_url = redirect_to_dashboard(user).url
            return JsonResponse({'redirect_url': redirect_url})
        else:
            return JsonResponse({'error': 'Invalid credentials'}, status=400)

    return render(request, 'login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "Logged out successfully.")
    return redirect('login')

def redirect_to_dashboard(user):
    """Redirect users to the appropriate dashboard based on their role."""
    if user.role == 'admin':
        return redirect('admin_dashboard')
    elif user.role == 'device-administrator':
        return redirect('device_admin_dashboard')
    elif user.role == 'user':
        return redirect('user_dashboard')
    else:
        return HttpResponseForbidden("Invalid user role.")


@login_required
def user_dashboard(request):
    if request.user.role != 'user':
        return HttpResponseForbidden("Access denied.")

    # Fetch devices assigned to the logged-in user
    user_devices = Device.objects.filter(user=request.user)
    
    # Get user's current settings
    user_settings = {
        'email_notifications': request.user.email_notifications,
        'update_interval': request.user.update_interval
    }
    
    # Get alerts for the user from both Alert and EmailLog models
    from mailer.models import Alert, EmailLog
    
    # Get alerts from Alert model
    alerts = Alert.objects.filter(user=request.user).order_by('-timestamp')
    
    # Get email logs for user's devices
    email_logs = EmailLog.objects.filter(
        device__in=user_devices,
        email_type='alert'
    ).order_by('-sent_at')
    
    # Combine alerts and email logs
    all_alerts = []
    
    # Add Alert model entries
    for alert in alerts:
        all_alerts.append({
            'title': alert.title,
            'message': alert.message,
            'severity': alert.severity,
            'timestamp': alert.timestamp,
            'device_id': alert.device.device_id if alert.device else None,
            'is_read': alert.is_read,
            'type': 'alert'
        })
    
    # Add EmailLog entries
    for log in email_logs:
        all_alerts.append({
            'title': log.subject,
            'message': f"Email sent to {log.recipient_email}",
            'severity': 'high' if 'Alert' in log.subject else 'medium',
            'timestamp': log.sent_at,
            'device_id': log.device.device_id,
            'is_read': True,
            'type': 'email'
        })
    
    # Sort all alerts by timestamp
    all_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Count unread alerts
    unread_alerts_count = sum(1 for alert in all_alerts if not alert.get('is_read', True))
    
    esp_devices = Device.objects.filter(
        user=request.user,
        device_type__in=['esp', 'esp8266', 'esp32']
    )
    
    context = {
        'user_devices': user_devices,
        'user_settings': user_settings,
        'alerts': all_alerts,
        'total_devices': user_devices.count(),
        'active_devices': user_devices.filter(device_status='online').count(),
        'unread_alerts': unread_alerts_count,
        'esp_devices': esp_devices,
    }
    
    return render(request, 'user_dashboard.html', context)

@login_required
def view_user_devices(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    devices = Device.objects.filter(user=user)
    return render(request, 'user_devices.html', {'user': user, 'devices': devices})

@login_required
def update_user_settings(request):
    if request.method == 'POST':
        try:
            user = request.user
            email_notifications = request.POST.get('email_notifications')
            update_interval = request.POST.get('update_interval')
            
            # Update user settings
            user.email_notifications = email_notifications
            user.update_interval = update_interval
            user.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def home(request):
    """
    Render the homepage with key features and authentication options
    """
    return render(request, 'home.html')


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt
def update_system_settings(request):
    if request.method == "POST":
        # Process and save settings here
        # Example: system_name = request.POST.get('system_name')
        # Save to your model or config
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Invalid request'}, status=400)

def device_config(request, device_id):
    device = get_object_or_404(Device, device_id=device_id, user=request.user)
    return render(request, 'devices/config.html', {'device': device})