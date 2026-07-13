from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser


class SignupAndRoleManagementTests(TestCase):
    def test_signup_defaults_to_user_role(self):
        response = self.client.post(
            reverse('signup'),
            {
                'username': 'newuser',
                'email': 'newuser@example.com',
                'password': 'StrongPass123',
                'password2': 'StrongPass123',
            },
        )

        self.assertEqual(response.status_code, 200)
        user = CustomUser.objects.get(username='newuser')
        self.assertEqual(user.role, 'user')

    def test_admin_can_make_existing_user_a_device_admin(self):
        admin = CustomUser.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='StrongPass123',
            role='admin',
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        user = CustomUser.objects.create_user(
            username='member',
            email='member@example.com',
            password='StrongPass123',
            role='user',
        )

        self.client.force_login(admin)
        response = self.client.post(
            reverse('admin_dashboard'),
            {
                'action': 'update_user_role',
                'user_id': user.id,
                'role': 'device-administrator',
            },
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.role, 'device-administrator')
