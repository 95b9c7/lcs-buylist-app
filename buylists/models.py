from decimal import Decimal

from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.customer.name} — {self.get_status_display()}'

    @property
    def total_market_value(self):
        return sum(item.line_market_value for item in self.items.all())

    @property
    def total_cash_offer_value(self):
        return sum(item.cash_offer_price for item in self.items.all())

    @property
    def total_trade_offer_value(self):
        return sum(item.trade_offer_price for item in self.items.all())

    @property
    def total_offer_value(self):
        """Trade credit total shown on customer offer sheets."""
        return self.total_trade_offer_value


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
        return Decimal(self.quantity) * self.market_price

    @property
    def offer_price(self):
        """Trade credit offer shown on customer offer sheets."""
        return self.trade_offer_price

    def _base_offer_value(self):
        return (
            Decimal(self.quantity)
            * self.market_price
            * self.condition_percent
        )

    def calculate_cash_offer_price(self):
        return (
            self._base_offer_value() * self.CASH_OFFER_PERCENT
        ).quantize(Decimal('0.01'))

    def calculate_trade_offer_price(self):
        return (
            self._base_offer_value() * self.TRADE_OFFER_PERCENT
        ).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        self.cash_offer_price = self.calculate_cash_offer_price()
        self.trade_offer_price = self.calculate_trade_offer_price()
        super().save(*args, **kwargs)
