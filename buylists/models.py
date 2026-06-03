from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

MONEY_PRECISION = Decimal('0.01')


def round_money(amount):
    """Round a money value to the nearest cent (hundredths place)."""
    return Decimal(amount).quantize(MONEY_PRECISION)


class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Buylist(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_WAITING = 'waiting'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_PAID = 'paid'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_WAITING, 'Waiting'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PAID, 'Paid'),
    ]

    PAYMENT_CASH = 'cash'
    PAYMENT_TRADE = 'trade'

    PAYMENT_CHOICES = [
        ('', 'Not selected'),
        (PAYMENT_CASH, 'Cash (60%)'),
        (PAYMENT_TRADE, 'Trade credit (70%)'),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='buylists',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    payment_choice = models.CharField(
        max_length=10,
        choices=PAYMENT_CHOICES,
        blank=True,
        default='',
    )

    PAYMENT_METHOD_CASH = 'cash'
    PAYMENT_METHOD_STORE_CREDIT = 'store_credit'
    PAYMENT_METHOD_TRADE = 'trade'
    PAYMENT_METHOD_MIXED = 'mixed'

    PAYMENT_METHOD_CHOICES = [
        ('', 'Not paid yet'),
        (PAYMENT_METHOD_CASH, 'Cash'),
        (PAYMENT_METHOD_STORE_CREDIT, 'Store credit'),
        (PAYMENT_METHOD_TRADE, 'Trade'),
        (PAYMENT_METHOD_MIXED, 'Mixed'),
    ]

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default='',
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='buylists_paid',
    )
    unlock_reason = models.TextField(blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='buylists_unlocked',
    )
    unlocked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.customer.name} — {self.get_status_display()}'

    @property
    def total_adjusted_market_value(self):
        """Sum of condition-adjusted line values before the offer rate."""
        return round_money(
            sum(item.adjusted_line_value for item in self.items.all())
        )

    @property
    def total_market_value(self):
        return round_money(sum(item.line_market_value for item in self.items.all()))

    @property
    def total_cash_offer_value(self):
        return round_money(
            self.total_adjusted_market_value * BuylistItem.CASH_OFFER_PERCENT
        )

    @property
    def total_trade_offer_value(self):
        return round_money(
            self.total_adjusted_market_value * BuylistItem.TRADE_OFFER_PERCENT
        )

    @property
    def total_recommended_offer_value(self):
        total_adjusted = self.total_adjusted_market_value
        if total_adjusted == 0:
            return round_money(0)
        offer_percent = BuylistItem.get_offer_percent_for_buylist(self)
        return round_money(total_adjusted * offer_percent)

    @property
    def total_final_offer_value(self):
        return round_money(sum(item.final_offer_price for item in self.items.all()))

    @property
    def payment_choice_selected(self):
        return bool(self.payment_choice)

    @property
    def total_offer_value(self):
        """Totals use the employee-approved final offer."""
        return self.total_final_offer_value

    @property
    def override_item_count(self):
        return self.items.filter(override_at__isnull=False).count()

    @property
    def is_paid(self):
        return self.status == self.STATUS_PAID

    @property
    def is_unlocked(self):
        return bool(self.unlocked_at)

    def clear_item_unlock(self):
        self.unlock_reason = ''
        self.unlocked_by = None
        self.unlocked_at = None

    @staticmethod
    def _allocate_proportionally(items, total_amount, value_getter):
        """Split a buylist-level total across items by each line's share."""
        if not items or total_amount == 0:
            return {item.pk: round_money(0) for item in items}

        total_base = sum(value_getter(item) for item in items)
        if total_base == 0:
            return {item.pk: round_money(0) for item in items}

        allocations = {}
        allocated = Decimal('0')
        for index, item in enumerate(items):
            if index == len(items) - 1:
                allocations[item.pk] = round_money(total_amount - allocated)
            else:
                share = round_money(total_amount * value_getter(item) / total_base)
                allocations[item.pk] = share
                allocated += share
        return allocations

    def estimate_item_recommended_offer(self, item, *, replace_pk=None):
        """
        Estimate one item's recommended offer using buylist-level rates.

        Pass replace_pk when simulating an edit to an existing item.
        """
        items = []
        for existing in self.items.all():
            if replace_pk and existing.pk == replace_pk:
                continue
            items.append(existing)
        items.append(item)
        items.sort(key=lambda row: row.pk or 0)

        total_adjusted = round_money(
            sum(row.adjusted_line_value for row in items)
        )
        if total_adjusted == 0:
            return round_money(0)

        offer_percent = BuylistItem.get_offer_percent_for_buylist(self)
        total_recommended = round_money(total_adjusted * offer_percent)
        return round_money(
            total_recommended * item.adjusted_line_value / total_adjusted
        )

    def recalculate_offer_allocations(
        self,
        override_user=None,
        new_item_id=None,
        reset_final_offers=False,
    ):
        """
        Apply cash/trade/recommended rates to the buylist total, then split
        each total proportionally across line items.

        When reset_final_offers is True (e.g. payment choice changed), set each
        line's final offer to the new recommended amount.
        """
        items = list(self.items.order_by('pk'))
        total_adjusted = round_money(
            sum(item.adjusted_line_value for item in items)
        )

        if not items or total_adjusted == 0:
            totals = {
                'cash': round_money(0),
                'trade': round_money(0),
                'recommended': round_money(0),
            }
        else:
            totals = {
                'cash': round_money(
                    total_adjusted * BuylistItem.CASH_OFFER_PERCENT
                ),
                'trade': round_money(
                    total_adjusted * BuylistItem.TRADE_OFFER_PERCENT
                ),
                'recommended': round_money(
                    total_adjusted
                    * BuylistItem.get_offer_percent_for_buylist(self)
                ),
            }

        value_getter = lambda row: row.adjusted_line_value
        cash_map = self._allocate_proportionally(items, totals['cash'], value_getter)
        trade_map = self._allocate_proportionally(items, totals['trade'], value_getter)
        recommended_map = self._allocate_proportionally(
            items, totals['recommended'], value_getter,
        )

        for item in items:
            item.cash_offer_price = cash_map[item.pk]
            item.trade_offer_price = trade_map[item.pk]
            item.recommended_offer_price = recommended_map[item.pk]
            if reset_final_offers or item.pk == new_item_id:
                item.final_offer_price = item.recommended_offer_price
            else:
                item.final_offer_price = round_money(item.final_offer_price)
            item.apply_override_tracking(override_user)
            item.save(skip_recalc=True, override_user=override_user)


class BuylistItem(models.Model):
    CONDITION_NM = 'NM'
    CONDITION_LP = 'LP'
    CONDITION_MP = 'MP'
    CONDITION_HP = 'HP'
    CONDITION_DMG = 'DMG'
    CONDITION_SEALED = 'SLD'

    CONDITION_CHOICES = [
        (CONDITION_NM, 'Near Mint (NM)'),
        (CONDITION_LP, 'Lightly Played (LP)'),
        (CONDITION_MP, 'Moderately Played (MP)'),
        (CONDITION_HP, 'Heavily Played (HP)'),
        (CONDITION_DMG, 'Damaged (DMG)'),
        (CONDITION_SEALED, 'Sealed'),
    ]

    SINGLES_CONDITION_CHOICES = [
        (CONDITION_NM, 'Near Mint (NM)'),
        (CONDITION_LP, 'Lightly Played (LP)'),
        (CONDITION_MP, 'Moderately Played (MP)'),
        (CONDITION_HP, 'Heavily Played (HP)'),
        (CONDITION_DMG, 'Damaged (DMG)'),
    ]

    CONDITION_DEFAULTS = {
        CONDITION_NM: Decimal('1.00'),
        CONDITION_LP: Decimal('0.90'),
        CONDITION_MP: Decimal('0.75'),
        CONDITION_HP: Decimal('0.60'),
        CONDITION_DMG: Decimal('0.40'),
        CONDITION_SEALED: Decimal('1.00'),
    }

    CASH_OFFER_PERCENT = Decimal('0.60')
    TRADE_OFFER_PERCENT = Decimal('0.70')

    buylist = models.ForeignKey(
        Buylist,
        on_delete=models.CASCADE,
        related_name='items',
    )
    card_name = models.CharField(max_length=200)
    set_name = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(
        max_length=3,
        choices=CONDITION_CHOICES,
        default=CONDITION_NM,
    )
    market_price = models.DecimalField(max_digits=10, decimal_places=2)
    condition_percent = models.DecimalField(max_digits=4, decimal_places=2)
    cash_offer_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    trade_offer_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    recommended_offer_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    final_offer_price = models.DecimalField(max_digits=10, decimal_places=2)
    override_reason = models.TextField(blank=True)
    override_recommended_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text='Recommended offer at the time of override.',
    )
    override_final_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text='Final offer recorded at the time of override.',
    )
    override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='offer_overrides',
    )
    override_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['card_name']

    def __str__(self):
        return self.card_name

    @classmethod
    def condition_percent_for(cls, condition):
        return cls.CONDITION_DEFAULTS.get(condition, Decimal('1.00'))

    @classmethod
    def condition_choices_for_product(cls, is_sealed=False):
        if is_sealed:
            return [
                (cls.CONDITION_SEALED, dict(cls.CONDITION_CHOICES)[cls.CONDITION_SEALED]),
            ]
        return cls.SINGLES_CONDITION_CHOICES

    @property
    def is_sealed(self):
        return self.condition == self.CONDITION_SEALED

    @property
    def line_market_value(self):
        return round_money(Decimal(self.quantity) * self.market_price)

    @property
    def adjusted_line_value(self):
        """Condition-adjusted value before the buylist offer rate is applied."""
        return round_money(
            Decimal(self.quantity) * self.market_price * self.condition_percent
        )

    @property
    def offer_percent(self):
        return self.get_offer_percent_for_buylist(self.buylist)

    @classmethod
    def get_offer_percent_for_buylist(cls, buylist):
        if buylist.payment_choice == Buylist.PAYMENT_CASH:
            return cls.CASH_OFFER_PERCENT
        if buylist.payment_choice == Buylist.PAYMENT_TRADE:
            return cls.TRADE_OFFER_PERCENT
        return cls.TRADE_OFFER_PERCENT

    @property
    def offer_price(self):
        return self.final_offer_price

    @property
    def is_offer_overridden(self):
        return self.final_offer_price > self.recommended_offer_price

    @property
    def has_override_record(self):
        return self.override_at is not None

    @property
    def override_difference(self):
        if not self.is_offer_overridden:
            return Decimal('0.00')
        base = self.override_recommended_price or self.recommended_offer_price
        final = self.override_final_price or self.final_offer_price
        return round_money(final - base)

    def apply_override_tracking(self, user=None):
        """Snapshot override details when final offer is above recommended."""
        if self.final_offer_price > self.recommended_offer_price:
            self.override_recommended_price = self.recommended_offer_price
            self.override_final_price = self.final_offer_price
            if user and user.is_authenticated:
                self.override_by = user
            self.override_at = timezone.now()
        else:
            self.override_recommended_price = None
            self.override_final_price = None
            self.override_reason = ''
            self.override_by = None
            self.override_at = None

    def _base_offer_value(self):
        return self.adjusted_line_value

    def calculate_cash_offer_price(self):
        return self._estimate_share_of_buylist_total(
            self.buylist.total_adjusted_market_value * self.CASH_OFFER_PERCENT,
        )

    def calculate_trade_offer_price(self):
        return self._estimate_share_of_buylist_total(
            self.buylist.total_adjusted_market_value * self.TRADE_OFFER_PERCENT,
        )

    def _estimate_share_of_buylist_total(self, buylist_total):
        if not self.buylist_id:
            return round_money(0)
        total_adjusted = self.buylist.total_adjusted_market_value
        if total_adjusted == 0:
            return round_money(0)
        return round_money(buylist_total * self.adjusted_line_value / total_adjusted)

    def calculate_recommended_offer_price(self):
        if not self.buylist_id:
            return round_money(0)
        return self.buylist.estimate_item_recommended_offer(
            self,
            replace_pk=self.pk,
        )

    def save(self, *args, override_user=None, skip_recalc=False, **kwargs):
        if skip_recalc:
            super().save(*args, **kwargs)
            return

        is_new = self._state.adding
        if is_new:
            self.cash_offer_price = round_money(0)
            self.trade_offer_price = round_money(0)
            self.recommended_offer_price = round_money(0)
            self.final_offer_price = round_money(0)
        else:
            self.final_offer_price = round_money(self.final_offer_price)

        super().save(*args, **kwargs)
        self.buylist.recalculate_offer_allocations(
            override_user=override_user,
            new_item_id=self.pk if is_new else None,
        )


class PricingRule(models.Model):
    name = models.CharField(max_length=100)
    min_market_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    max_market_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Leave blank for no upper limit.',
    )
    offer_percent = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text='Store rate as decimal (0.70 = 70%).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['min_market_price', 'name']
        verbose_name = 'pricing rule'
        verbose_name_plural = 'pricing rules'

    def __str__(self):
        if self.max_market_price is not None:
            return f'{self.name} (${self.min_market_price}–${self.max_market_price})'
        return f'{self.name} (${self.min_market_price}+)'


class BuylistActivity(models.Model):
    ACTION_BUYLIST_CREATED = 'buylist_created'
    ACTION_ITEM_ADDED = 'item_added'
    ACTION_ITEM_UPDATED = 'item_updated'
    ACTION_ITEM_DELETED = 'item_deleted'
    ACTION_STATUS_CHANGED = 'status_changed'
    ACTION_OFFER_PRINTED = 'offer_printed'
    ACTION_CSV_EXPORTED = 'csv_exported'
    ACTION_PAYMENT_RECORDED = 'payment_recorded'
    ACTION_OVERRIDE_ADDED = 'override_added'

    ACTION_CHOICES = [
        (ACTION_BUYLIST_CREATED, 'Buylist created'),
        (ACTION_ITEM_ADDED, 'Item added'),
        (ACTION_ITEM_UPDATED, 'Item updated'),
        (ACTION_ITEM_DELETED, 'Item deleted'),
        (ACTION_STATUS_CHANGED, 'Status changed'),
        (ACTION_OFFER_PRINTED, 'Offer printed'),
        (ACTION_CSV_EXPORTED, 'CSV exported'),
        (ACTION_PAYMENT_RECORDED, 'Payment recorded'),
        (ACTION_OVERRIDE_ADDED, 'Override added'),
    ]

    buylist = models.ForeignKey(
        Buylist,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='buylist_activities',
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'buylist activities'

    def __str__(self):
        return f'{self.buylist_id} — {self.get_action_display()}'

