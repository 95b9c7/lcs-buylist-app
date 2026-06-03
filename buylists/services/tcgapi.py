from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from ..models import round_money

SEARCH_URL = 'https://api.tcgapi.dev/v1/search'
DEFAULT_TIMEOUT = 15


class TCGApiKeyMissingError(Exception):
    """TCGAPI_KEY environment variable is not set."""


class TCGApiRequestError(Exception):
    """The TCG API request failed."""


def _get_api_key():
    api_key = getattr(settings, 'TCGAPI_KEY', '') or ''
    if not api_key.strip():
        raise TCGApiKeyMissingError(
            'TCGAPI_KEY is not configured. Set it in your environment.'
        )
    return api_key.strip()


def _parse_price(value):
    """Turn API price values into a rounded Decimal or None."""
    if value is None or value == '':
        return None

    if isinstance(value, dict):
        for key in ('market', 'market_price', 'price', 'mid', 'average', 'low'):
            if key in value and value[key] is not None:
                parsed = _parse_price(value[key])
                if parsed is not None:
                    return parsed
        return None

    try:
        return round_money(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_set(value):
    if isinstance(value, dict):
        return (
            value.get('name')
            or value.get('set_name')
            or value.get('title')
            or ''
        )
    return str(value) if value is not None else ''


def _normalize_card(raw):
    """Map one API result into a simple dict for templates."""
    prices = raw.get('prices') if isinstance(raw.get('prices'), dict) else {}

    price = _parse_price(
        raw.get('price')
        or raw.get('market_price')
        or prices.get('market')
        or prices.get('price')
    )
    low_price = _parse_price(
        raw.get('low_price')
        or raw.get('low')
        or prices.get('low')
        or prices.get('low_price')
    )
    foil_price = _parse_price(
        raw.get('foil_price')
        or raw.get('foil')
        or prices.get('foil')
        or prices.get('foil_price')
    )

    set_name = _parse_set(raw.get('set') or raw.get('set_name'))

    number = raw.get('number') or raw.get('collector_number') or raw.get('card_number') or ''

    return {
        'id': raw.get('id') or raw.get('card_id') or '',
        'name': raw.get('name') or raw.get('card_name') or '',
        'set': set_name,
        'number': str(number) if number is not None else '',
        'rarity': raw.get('rarity') or '',
        'price': price,
        'low_price': low_price,
        'foil_price': foil_price,
    }


def _extract_results(payload):
    """Read the card list from common API response shapes."""
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ('data', 'results', 'cards', 'items'):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def search_cards(query, game='pokemon'):
    """
    Search TCGApi.dev for cards.

    Returns a list of dicts with id, name, set, number, rarity,
    price, low_price, and foil_price.
    """
    query = (query or '').strip()
    if not query:
        return []

    api_key = _get_api_key()

    try:
        response = requests.get(
            SEARCH_URL,
            params={'q': query, 'game': game},
            headers={'X-API-Key': api_key},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise TCGApiRequestError(f'TCG API request failed: {exc}') from exc
    except ValueError as exc:
        raise TCGApiRequestError('TCG API returned invalid JSON.') from exc

    results = []
    for raw in _extract_results(payload):
        if isinstance(raw, dict):
            card = _normalize_card(raw)
            if card['name']:
                results.append(card)

    return results
