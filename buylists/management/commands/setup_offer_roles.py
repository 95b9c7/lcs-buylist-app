from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create Django groups for offer override roles (Employee, Manager, Owner, Admin).'

    def handle(self, *args, **options):
        for name in ['Employee', 'Manager', 'Owner', 'Admin']:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group: {name}'))
            else:
                self.stdout.write(f'Group already exists: {name}')

        self.stdout.write(
            '\nAssign users to groups in Django admin. '
            'Users without Manager/Owner/Admin are treated as Employee (5% max override). '
            'Superusers have unlimited override.'
        )
