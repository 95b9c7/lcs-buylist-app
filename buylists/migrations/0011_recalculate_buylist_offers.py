from decimal import Decimal

from django.db import migrations


def recalculate_all_buylist_offers(apps, schema_editor):
    Buylist = apps.get_model('buylists', 'Buylist')
    for buylist in Buylist.objects.prefetch_related('items'):
        items = list(buylist.items.order_by('pk'))
        if not items:
            continue

        total_adjusted = sum(
            (
                Decimal(str(item.quantity))
                * item.market_price
                * item.condition_percent
            ).quantize(Decimal('0.01'))
            for item in items
        )
        total_adjusted = total_adjusted.quantize(Decimal('0.01'))

        if buylist.payment_choice == 'cash':
            offer_percent = Decimal('0.60')
        else:
            offer_percent = Decimal('0.70')

        cash_total = (total_adjusted * Decimal('0.60')).quantize(Decimal('0.01'))
        trade_total = (total_adjusted * Decimal('0.70')).quantize(Decimal('0.01'))
        recommended_total = (total_adjusted * offer_percent).quantize(Decimal('0.01'))

        def allocate(total_amount):
            if total_adjusted == 0:
                return {item.pk: Decimal('0.00') for item in items}
            allocations = {}
            allocated = Decimal('0.00')
            for index, item in enumerate(items):
                line_value = (
                    Decimal(str(item.quantity))
                    * item.market_price
                    * item.condition_percent
                ).quantize(Decimal('0.01'))
                if index == len(items) - 1:
                    allocations[item.pk] = (total_amount - allocated).quantize(
                        Decimal('0.01')
                    )
                else:
                    share = (total_amount * line_value / total_adjusted).quantize(
                        Decimal('0.01')
                    )
                    allocations[item.pk] = share
                    allocated += share
            return allocations

        cash_map = allocate(cash_total)
        trade_map = allocate(trade_total)
        recommended_map = allocate(recommended_total)

        BuylistItem = apps.get_model('buylists', 'BuylistItem')
        for item in items:
            BuylistItem.objects.filter(pk=item.pk).update(
                cash_offer_price=cash_map[item.pk],
                trade_offer_price=trade_map[item.pk],
                recommended_offer_price=recommended_map[item.pk],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0010_buylist_activity'),
    ]

    operations = [
        migrations.RunPython(
            recalculate_all_buylist_offers,
            migrations.RunPython.noop,
        ),
    ]
