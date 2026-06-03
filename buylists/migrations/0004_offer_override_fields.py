from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_offer_fields(apps, schema_editor):
    Buylist = apps.get_model('buylists', 'Buylist')
    BuylistItem = apps.get_model('buylists', 'BuylistItem')

    for item in BuylistItem.objects.select_related('buylist').all():
        buylist = item.buylist
        base = (
            Decimal(item.quantity)
            * item.market_price
            * item.condition_percent
        )
        if buylist.payment_choice == 'cash':
            recommended = (base * Decimal('0.60')).quantize(Decimal('0.01'))
        else:
            recommended = (base * Decimal('0.70')).quantize(Decimal('0.01'))

        item.recommended_offer_price = recommended
        if buylist.payment_choice == 'cash':
            item.final_offer_price = item.cash_offer_price
        else:
            item.final_offer_price = item.trade_offer_price
        item.save(update_fields=['recommended_offer_price', 'final_offer_price'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('buylists', '0003_buylist_payment_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='buylistitem',
            name='recommended_offer_price',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), editable=False, max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='final_offer_price',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='override_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='override_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='offer_overrides',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='override_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(populate_offer_fields, migrations.RunPython.noop),
    ]
