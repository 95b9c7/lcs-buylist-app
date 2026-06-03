import csv
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Buylist, BuylistItem, Customer


class BuylistCsvExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='employee',
            password='password',
        )
        self.client.force_login(self.user)

    def _create_buylist(self, customer_name, *, status=Buylist.STATUS_DRAFT):
        customer = Customer.objects.create(name=customer_name)
        return Buylist.objects.create(customer=customer, status=status)

    def _add_item(self, buylist, card_name, *, market_price='10.00'):
        return BuylistItem.objects.create(
            buylist=buylist,
            card_name=card_name,
            set_name='Test Set',
            quantity=2,
            condition=BuylistItem.CONDITION_NM,
            condition_percent=Decimal('1.00'),
            market_price=Decimal(market_price),
        )

    def _csv_rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def test_single_buylist_csv_export_keeps_existing_item_columns(self):
        buylist = self._create_buylist('Alice Buyer')
        self._add_item(buylist, 'Lightning Bolt')

        response = self.client.get(
            reverse('buylists:buylist_export_csv', kwargs={'pk': buylist.pk}),
        )

        rows = self._csv_rows(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(rows[0], [
            'Buylist ID',
            'Customer Name',
            'Card Name',
            'Set Name',
            'Quantity',
            'Condition',
            'Market Price',
            'Offer Percent',
            'Recommended Offer Price',
            'Final Offer Price',
            'Override Reason',
            'Override Recommended',
            'Override Final',
            'Override By',
            'Override At',
            'Notes',
        ])
        self.assertEqual(rows[1][0:4], [
            str(buylist.pk),
            'Alice Buyer',
            'Lightning Bolt',
            'Test Set',
        ])

    def test_bulk_buylist_csv_export_uses_filters_and_includes_empty_buylists(self):
        matching_with_item = self._create_buylist(
            'Alice Buyer',
            status=Buylist.STATUS_ACCEPTED,
        )
        matching_empty = self._create_buylist(
            'Alice Seller',
            status=Buylist.STATUS_ACCEPTED,
        )
        filtered_out = self._create_buylist(
            'Bob Buyer',
            status=Buylist.STATUS_ACCEPTED,
        )
        self._add_item(matching_with_item, 'Sol Ring')
        self._add_item(filtered_out, 'Counterspell')

        response = self.client.get(
            reverse('buylists:buylist_bulk_export_csv'),
            {'q': 'Alice', 'status': Buylist.STATUS_ACCEPTED},
        )

        rows = self._csv_rows(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(
            'attachment; filename="buylists_export_',
            response['Content-Disposition'],
        )
        self.assertEqual(rows[0][0:12], [
            'Buylist ID',
            'Customer Name',
            'Buylist Status',
            'Payment Choice',
            'Payment Method',
            'Amount Paid',
            'Paid At',
            'Created At',
            'Updated At',
            'Total Market Value',
            'Total Offer Value',
            'Card Name',
        ])

        exported_ids = {row[0] for row in rows[1:]}
        self.assertEqual(exported_ids, {
            str(matching_with_item.pk),
            str(matching_empty.pk),
        })
        self.assertNotIn(str(filtered_out.pk), exported_ids)

        item_row = next(row for row in rows[1:] if row[0] == str(matching_with_item.pk))
        self.assertEqual(item_row[1], 'Alice Buyer')
        self.assertEqual(item_row[2], 'Accepted')
        self.assertEqual(item_row[11], 'Sol Ring')

        empty_row = next(row for row in rows[1:] if row[0] == str(matching_empty.pk))
        self.assertEqual(empty_row[1], 'Alice Seller')
        self.assertEqual(empty_row[11:], [''] * 14)
