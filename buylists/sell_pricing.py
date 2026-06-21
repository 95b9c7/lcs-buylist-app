"""In-store sell prices derived from JustTCG Near Mint market pricing."""

from decimal import Decimal

from .models import BuylistItem, round_money

SELL_PRICE_MARKUP = Decimal('0.10')

SINGLES_CONDITION_FACTORS = {
    BuylistItem.CONDITION_NM: Decimal('1.00'),
    BuylistItem.CONDITION_LP: Decimal('0.80'),
    BuylistItem.CONDITION_MP: Decimal('0.65'),
    BuylistItem.CONDITION_HP: Decimal('0.30'),
    BuylistItem.CONDITION_DMG: Decimal('0.15'),
}


def calculate_sell_prices(nm_market):
    """
    Compute shelf sell prices for each singles condition.

    Formula: (Near Mint market × condition factor) + 10% markup.
    """
    nm_market = round_money(nm_market)
    rows = []
    for condition, factor in SINGLES_CONDITION_FACTORS.items():
        adjusted_base = round_money(nm_market * factor)
        sell_price = round_money(adjusted_base * (Decimal('1') + SELL_PRICE_MARKUP))
        rows.append({
            'condition': condition,
            'label': dict(BuylistItem.CONDITION_CHOICES)[condition],
            'factor': factor,
            'adjusted_base': adjusted_base,
            'sell_price': sell_price,
        })
    return rows


def calculate_sealed_sell_price(market_price):
    """Sealed products use market price + 10% markup."""
    market_price = round_money(market_price)
    return round_money(market_price * (Decimal('1') + SELL_PRICE_MARKUP))
