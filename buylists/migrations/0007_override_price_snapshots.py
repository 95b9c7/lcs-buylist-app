from django.db import migrations, models


def backfill_override_snapshots(apps, schema_editor):
    BuylistItem = apps.get_model('buylists', 'BuylistItem')

    for item in BuylistItem.objects.filter(override_at__isnull=False):
        item.override_recommended_price = item.recommended_offer_price
        item.override_final_price = item.final_offer_price
        item.save(
            update_fields=['override_recommended_price', 'override_final_price']
        )


class Migration(migrations.Migration):

    dependencies = [
        ('buylists', '0006_round_offer_prices'),
    ]

    operations = [
        migrations.AddField(
            model_name='buylistitem',
            name='override_final_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                editable=False,
                help_text='Final offer recorded at the time of override.',
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='buylistitem',
            name='override_recommended_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                editable=False,
                help_text='Recommended offer at the time of override.',
                max_digits=10,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_override_snapshots, migrations.RunPython.noop),
    ]
