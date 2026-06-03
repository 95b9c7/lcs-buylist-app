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
    def total_market_value(self):
        return round_money(sum(item.line_market_value for item in self.items.all()))

    @property
    def total_cash_offer_value(self):
        return round_money(sum(item.cash_offer_price for item in self.items.all()))

    @property
    def total_trade_offer_value(self):
        return round_money(sum(item.trade_offer_price for item in self.items.all()))

    @property
    def total_recommended_offer_value(self):
        return round_money(
            sum(item.recommended_offer_price for item in self.items.all())
        )

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


class BuylistItem(models.Model):
    CONDITION_NM = 'NM'
    CONDITION_LP = 'LP'
    CONDITION_MP = 'MP'
    CONDITION_HP = 'HP'
    CONDITION_DMG = 'DMG'

    CONDITION_CHOICES = [
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

    @property
    def line_market_value(self):
        return round_money(Decimal(self.quantity) * self.market_price)

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
        return (
            Decimal(self.quantity)
            * self.market_price
            * self.condition_percent
        )

    def calculate_cash_offer_price(self):
        return round_money(self._base_offer_value() * self.CASH_OFFER_PERCENT)

    def calculate_trade_offer_price(self):
        return round_money(self._base_offer_value() * self.TRADE_OFFER_PERCENT)

    def calculate_recommended_offer_price(self):
        offer_percent = self.get_offer_percent_for_buylist(self.buylist)
        return round_money(self._base_offer_value() * offer_percent)

    def save(self, *args, override_user=None, **kwargs):
        self.cash_offer_price = self.calculate_cash_offer_price()
        self.trade_offer_price = self.calculate_trade_offer_price()
        self.recommended_offer_price = self.calculate_recommended_offer_price()

        if self._state.adding:
            self.final_offer_price = self.recommended_offer_price
        else:
            self.final_offer_price = round_money(self.final_offer_price)

        if not self._state.adding:
            self.apply_override_tracking(override_user)

        super().save(*args, **kwargs)


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

