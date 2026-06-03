from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0004_offer_override_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('min_market_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('max_market_price', models.DecimalField(blank=True, decimal_places=2, help_text='Leave blank for no upper limit.', max_digits=10, null=True)),
                ('offer_percent', models.DecimalField(decimal_places=2, help_text='Store rate as decimal (0.70 = 70%).', max_digits=4)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'pricing rule',
                'verbose_name_plural': 'pricing rules',
                'ordering': ['min_market_price', 'name'],
            },
        ),
    ]
