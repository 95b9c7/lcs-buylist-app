from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create staff groups: Employee, Manager, and Owner.'

    def handle(self, *args, **options):
        for name in ['Employee', 'Manager', 'Owner']:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group: {name}'))
            else:
                self.stdout.write(f'Group already exists: {name}')

        self.stdout.write(
            '\nAssign each user to one group in Django admin (Users).\n'
            '  Employee — buylists, customers, cards (5% max offer override)\n'
            '  Manager  — above + buylist status/payment settings (15% override)\n'
            '  Owner    — above + pricing rules (unlimited override)\n'
            '\nCreate users with: python manage.py createsuperuser'
        )
