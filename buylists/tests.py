from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Buylist, BuylistItem, Customer


class BuylistReportTests(TestCase):
    def setUp(self):
        self.employee_group = Group.objects.create(name='Employee')
        self.manager_group = Group.objects.create(name='Manager')

        User = get_user_model()
        self.alice = User.objects.create_user(
            username='alice',
            password='password',
        )
        self.alice.groups.add(self.employee_group)
        self.bob = User.objects.create_user(
            username='bob',
            password='password',
        )
        self.bob.groups.add(self.employee_group)
        self.manager = User.objects.create_user(
            username='manager',
            password='password',
        )
        self.manager.groups.add(self.manager_group)

    def _create_buylist(
        self,
        customer_name,
        *,
        status=Buylist.STATUS_DRAFT,
        created_by=None,
        completed_by=None,
        amount_paid=None,
    ):
        buylist = Buylist.objects.create(
            customer=Customer.objects.create(name=customer_name),
            status=status,
            created_by=created_by,
            completed_by=completed_by,
            completed_at=timezone.now() if completed_by else None,
            amount_paid=amount_paid,
        )
        BuylistItem.objects.create(
            buylist=buylist,
            card_name='Test Card',
            set_name='Test Set',
            quantity=1,
            condition=BuylistItem.CONDITION_NM,
            condition_percent=Decimal('1.00'),
            market_price=Decimal('10.00'),
        )
        return buylist

    def test_buylist_create_and_status_update_track_employee_activity(self):
        self.client.force_login(self.manager)
        customer = Customer.objects.create(name='Walk In')

        response = self.client.post(reverse('buylists:buylist_create'), {
            'customer': customer.pk,
            'status': Buylist.STATUS_DRAFT,
        })

        buylist = Buylist.objects.get(customer=customer)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(buylist.created_by, self.manager)
        self.assertIsNone(buylist.completed_by)
        self.assertIsNone(buylist.completed_at)

        response = self.client.post(
            reverse('buylists:buylist_update_status', kwargs={'pk': buylist.pk}),
            {
                'status': Buylist.STATUS_ACCEPTED,
                'payment_method': '',
                'amount_paid': '',
            },
        )

        buylist.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(buylist.status, Buylist.STATUS_ACCEPTED)
        self.assertEqual(buylist.completed_by, self.manager)
        self.assertIsNotNone(buylist.completed_at)

    def test_manager_report_filters_by_status_and_employee(self):
        paid_buylist = self._create_buylist(
            'Alice Paid',
            status=Buylist.STATUS_PAID,
            created_by=self.alice,
            completed_by=self.bob,
            amount_paid=Decimal('8.00'),
        )
        self._create_buylist(
            'Bob Rejected',
            status=Buylist.STATUS_REJECTED,
            created_by=self.bob,
            completed_by=self.bob,
        )
        self._create_buylist(
            'Alice Draft',
            status=Buylist.STATUS_DRAFT,
            created_by=self.alice,
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse('buylists:buylist_report'), {
            'period': 'today',
            'status': Buylist.STATUS_PAID,
            'employee': self.bob.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [buylist.pk for buylist in response.context['buylists']],
            [paid_buylist.pk],
        )
        self.assertEqual(response.context['summary']['total_buylists'], 1)
        self.assertEqual(
            response.context['summary']['total_paid_amount'],
            Decimal('8.00'),
        )
        self.assertContains(response, 'Alice Paid')
        self.assertContains(response, 'bob')
        self.assertContains(response, 'Print Report')

    def test_employee_report_ignores_other_employee_filter(self):
        own_buylist = self._create_buylist(
            'Alice Own',
            status=Buylist.STATUS_ACCEPTED,
            created_by=self.alice,
            completed_by=self.alice,
        )
        self._create_buylist(
            'Bob Own',
            status=Buylist.STATUS_ACCEPTED,
            created_by=self.bob,
            completed_by=self.bob,
        )
        self.client.force_login(self.alice)

        response = self.client.get(reverse('buylists:buylist_report'), {
            'period': 'today',
            'employee': self.bob.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_view_all_employees'])
        self.assertEqual(response.context['selected_employee_id'], str(self.alice.pk))
        self.assertEqual(
            [buylist.pk for buylist in response.context['buylists']],
            [own_buylist.pk],
        )
        self.assertEqual(
            [row['employee'] for row in response.context['employee_breakdown']],
            [self.alice],
        )
        self.assertContains(response, 'Alice Own')
        self.assertNotContains(response, 'Bob Own')

    def test_report_date_label_uses_cross_platform_formatting(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse('buylists:buylist_report'), {
            'period': 'custom',
            'start_date': '2026-06-03',
            'end_date': '2026-06-03',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['range_label'], 'Jun 3, 2026')
        self.assertContains(response, 'Jun 3, 2026')

    def test_authenticated_navbar_includes_reports_link(self):
        self.client.force_login(self.alice)

        response = self.client.get(reverse('buylists:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('buylists:buylist_report'))
        self.assertContains(response, 'Reports')
