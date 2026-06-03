from decimal import Decimal

from django.db import migrations, models


def populate_dual_offers(apps, schema_editor):
    BuylistItem = apps.get_model('buylists', 'BuylistItem')
    cash_rate = Decimal('0.60')
    trade_rate = Decimal('0.70')

    for item in BuylistItem.objects.all():
        base = (
            Decimal(item.quantity)
            * item.market_price
            * item.condition_percent
        )
        item.cash_offer_price = (base * cash_rate).quantize(Decimal('0.01'))
        item.trade_offer_price = (base * trade_rate).quantize(Decimal('0.01'))
        item.save(update_fields=['cash_offer_price', 'trade_offer_price'])


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='buylistitem',
            name='cash_offer_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                editable=False,
                max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='trade_offer_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                editable=False,
                max_digits=10,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(populate_dual_offers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='buylistitem',
            name='offer_percent',
        ),
        migrations.RemoveField(
            model_name='buylistitem',
            name='offer_price',
        ),
    ]
