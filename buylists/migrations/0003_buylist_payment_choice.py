from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0002_dual_offers'),
    ]

    operations = [
        migrations.AddField(
            model_name='buylist',
            name='payment_choice',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Not selected'),
                    ('cash', 'Cash (60%)'),
                    ('trade', 'Trade credit (70%)'),
                ],
                default='',
                max_length=10,
            ),
        ),
    ]
