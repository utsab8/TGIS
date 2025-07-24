from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create or update the default admin user (email: acharyautsab390@gmail.com, password: utsab12@)'

    def handle(self, *args, **kwargs):
        u, created = User.objects.get_or_create(username='acharyautsab390@gmail.com', defaults={'email': 'acharyautsab390@gmail.com'})
        u.email = 'acharyautsab390@gmail.com'
        u.set_password('utsab12@')
        u.is_staff = True
        u.is_superuser = True
        u.save()
        self.stdout.write(self.style.SUCCESS(f'Admin user created/updated: {u}')) 