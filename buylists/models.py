from decimal import Decimal

from django.conf import settings
from django.db import models

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

    def save(self, *args, **kwargs):
        self.cash_offer_price = self.calculate_cash_offer_price()
        self.trade_offer_price = self.calculate_trade_offer_price()
        self.recommended_offer_price = self.calculate_recommended_offer_price()

        if self._state.adding:
            self.final_offer_price = self.recommended_offer_price
        else:
            self.final_offer_price = round_money(self.final_offer_price)

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
