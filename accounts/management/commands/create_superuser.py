from django.core.management.base import BaseCommand
from accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Create the default admin superuser if it does not exist.'

    def handle(self, *args, **options):
        username = 'admin'
        email = 'admin@example.com'
        password = '@dmin123'

        if CustomUser.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User {username} already exists.'))
            return

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            role='admin',
        )
        user.is_staff = True
        user.is_superuser = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Created superuser {username} with password {password}'))
