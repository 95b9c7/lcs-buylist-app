from decimal import Decimal

from django.db import migrations


def round_existing_offers(apps, schema_editor):
    BuylistItem = apps.get_model('buylists', 'BuylistItem')
    precision = Decimal('0.01')

    for item in BuylistItem.objects.all():
        item.cash_offer_price = item.cash_offer_price.quantize(precision)
        item.trade_offer_price = item.trade_offer_price.quantize(precision)
        item.recommended_offer_price = item.recommended_offer_price.quantize(precision)
        item.final_offer_price = item.final_offer_price.quantize(precision)
        item.save(
            update_fields=[
                'cash_offer_price',
                'trade_offer_price',
                'recommended_offer_price',
                'final_offer_price',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0005_pricingrule'),
    ]

    operations = [
        migrations.RunPython(round_existing_offers, migrations.RunPython.noop),
    ]
