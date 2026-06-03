import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('buylists', '0007_override_price_snapshots'),
    ]

    operations = [
        migrations.AddField(
            model_name='buylist',
            name='amount_paid',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='buylist',
            name='paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='buylist',
            name='paid_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='buylists_paid',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='buylist',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Not paid yet'),
                    ('cash', 'Cash'),
                    ('store_credit', 'Store credit'),
                    ('trade', 'Trade'),
                    ('mixed', 'Mixed'),
                ],
                default='',
                max_length=20,
            ),
        ),
    ]
