from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from ..models import BuylistItem, round_money

BASE_URL = 'https://api.justtcg.com/v1'
DEFAULT_TIMEOUT = 15
# Free/starter JustTCG plans allow at most 20 results per request.
SEARCH_RESULT_LIMIT = 20

PRODUCT_TYPE_SINGLES = 'singles'
PRODUCT_TYPE_SEALED = 'sealed'
PRODUCT_TYPE_ALL = 'all'

# UI slugs -> JustTCG API game parameter values
GAME_SLUG_TO_API = {
    'pokemon': 'pokemon',
    'magic': 'magic-the-gathering',
    'yugioh': 'yugioh',
    'lorcana': 'disney-lorcana',
    'onepiece': 'one-piece-card-game',
}


def _api_game_param(game):
    if not game:
        return None
    slug = game.strip().lower()
    return GAME_SLUG_TO_API.get(slug, slug)

SINGLES_API_CONDITIONS = 'NM,LP,MP,HP,DMG'
SEALED_API_CONDITION = 'Sealed'

APP_TO_API_CONDITION = {
    BuylistItem.CONDITION_NM: 'NM',
    BuylistItem.CONDITION_LP: 'LP',
    BuylistItem.CONDITION_MP: 'MP',
    BuylistItem.CONDITION_HP: 'HP',
    BuylistItem.CONDITION_DMG: 'DMG',
    BuylistItem.CONDITION_SEALED: SEALED_API_CONDITION,
}

API_TO_APP_CONDITION = {
    'near mint': BuylistItem.CONDITION_NM,
    'nm': BuylistItem.CONDITION_NM,
    'lightly played': BuylistItem.CONDITION_LP,
    'lp': BuylistItem.CONDITION_LP,
    'moderately played': BuylistItem.CONDITION_MP,
    'mp': BuylistItem.CONDITION_MP,
    'heavily played': BuylistItem.CONDITION_HP,
    'hp': BuylistItem.CONDITION_HP,
    'damaged': BuylistItem.CONDITION_DMG,
    'dmg': BuylistItem.CONDITION_DMG,
    'sealed': BuylistItem.CONDITION_SEALED,
    's': BuylistItem.CONDITION_SEALED,
}


class JustTCGKeyMissingError(Exception):
    """JUSTTCG_API_KEY environment variable is not set."""


class JustTCGRequestError(Exception):
    """The JustTCG API request failed."""


class JustTCGPriceMissingError(Exception):
    """No price was returned for the requested card variant."""


def _get_api_key():
    api_key = getattr(settings, 'JUSTTCG_API_KEY', '') or ''
    if not api_key.strip():
        raise JustTCGKeyMissingError(
            'JUSTTCG_API_KEY is not configured. Add it to your .env file.'
        )
    return api_key.strip()


def _parse_price(value):
    if value is None or value == '':
        return None
    try:
        return round_money(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_condition_code(condition):
    code = (condition or BuylistItem.CONDITION_NM).strip()
    upper = code.upper()
    valid = dict(BuylistItem.CONDITION_CHOICES)
    if upper in valid:
        return upper
    mapped = API_TO_APP_CONDITION.get(code.lower())
    if mapped:
        return mapped
    return BuylistItem.CONDITION_NM


def _to_api_condition(condition_code):
    return APP_TO_API_CONDITION.get(
        _normalize_condition_code(condition_code),
        'NM',
    )


def _condition_matches(variant_condition, condition_code):
    variant_code = API_TO_APP_CONDITION.get(
        (variant_condition or '').strip().lower(),
        (variant_condition or '').strip().upper(),
    )
    return variant_code == _normalize_condition_code(condition_code)


def _detect_is_sealed(raw):
    variants = raw.get('variants') or []
    if not variants:
        return False
    conditions = {
        (variant.get('condition') or '').strip().lower()
        for variant in variants
    }
    return conditions == {'sealed'}


def _extract_data(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get('data')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        if payload.get('error'):
            raise JustTCGRequestError(payload['error'])
    return []


def _api_get(endpoint, params):
    api_key = _get_api_key()
    url = f'{BASE_URL}/{endpoint.lstrip("/")}'

    try:
        response = requests.get(
            url,
            params=params,
            headers={'x-api-key': api_key},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        detail = ''
        try:
            body = response.json()
            detail = body.get('error') or body.get('message') or ''
        except ValueError:
            detail = response.text[:200]
        message = detail or str(exc)
        raise JustTCGRequestError(f'JustTCG API request failed: {message}') from exc
    except requests.RequestException as exc:
        raise JustTCGRequestError(f'JustTCG API request failed: {exc}') from exc
    except ValueError as exc:
        raise JustTCGRequestError('JustTCG API returned invalid JSON.') from exc


def _normalize_search_card(raw):
    set_name = raw.get('set_name') or raw.get('set') or ''
    tcgplayer_id = raw.get('tcgplayerId') or raw.get('tcgplayer_id') or ''
    is_sealed = _detect_is_sealed(raw)

    return {
        'id': raw.get('id') or '',
        'name': raw.get('name') or '',
        'game': raw.get('game') or '',
        'set': set_name,
        'number': str(raw.get('number') or ''),
        'rarity': raw.get('rarity') or '',
        'tcgplayerId': str(tcgplayer_id) if tcgplayer_id else '',
        'is_sealed': is_sealed,
        'product_type': PRODUCT_TYPE_SEALED if is_sealed else PRODUCT_TYPE_SINGLES,
    }


def search_cards(query, game=None, product_type=PRODUCT_TYPE_SINGLES):
    """
    Search JustTCG for singles or sealed products.

    product_type: singles, sealed, or all
    """
    query = (query or '').strip()
    if not query:
        return []

    params = {'q': query, 'limit': SEARCH_RESULT_LIMIT}
    if game:
        params['game'] = _api_game_param(game)

    if product_type == PRODUCT_TYPE_SEALED:
        params['condition'] = SEALED_API_CONDITION
    elif product_type == PRODUCT_TYPE_SINGLES:
        params['condition'] = SINGLES_API_CONDITIONS

    payload = _api_get('cards', params)
    results = []
    for raw in _extract_data(payload):
        if isinstance(raw, dict):
            card = _normalize_search_card(raw)
            if not card['name']:
                continue
            if product_type == PRODUCT_TYPE_SINGLES and card['is_sealed']:
                continue
            if product_type == PRODUCT_TYPE_SEALED and not card['is_sealed']:
                continue
            results.append(card)
    return results


def _pick_variant(variants, condition_code, printing=None):
    condition_code = _normalize_condition_code(condition_code)
    matches = [
        variant for variant in variants
        if _condition_matches(variant.get('condition'), condition_code)
    ]
    if printing:
        printing_lower = printing.strip().lower()
        matches = [
            variant for variant in matches
            if (variant.get('printing') or '').strip().lower() == printing_lower
        ]

    if not matches:
        return None

    if not printing and condition_code != BuylistItem.CONDITION_SEALED:
        for variant in matches:
            if (variant.get('printing') or '').strip().lower() == 'normal':
                return variant

    priced = [
        variant for variant in matches
        if _parse_price(variant.get('price')) is not None
    ]
    if priced:
        return min(
            priced,
            key=lambda variant: _parse_price(variant.get('price')),
        )
    return matches[0]


def get_condition_price(card_id, condition, printing=None):
    """
    Fetch the market price for a card in a specific condition.

    Returns card_name, set_name, condition, printing, price, and is_sealed.
    """
    card_id = (card_id or '').strip()
    if not card_id:
        raise JustTCGRequestError('A card id is required to look up pricing.')

    condition_code = _normalize_condition_code(condition)
    params = {
        'cardId': card_id,
        'condition': _to_api_condition(condition_code),
    }
    if printing:
        params['printing'] = printing

    payload = _api_get('cards', params)
    cards = _extract_data(payload)
    if not cards:
        raise JustTCGPriceMissingError(
            'No pricing data found for this card and condition.'
        )

    card = cards[0]
    is_sealed = _detect_is_sealed(card) or condition_code == BuylistItem.CONDITION_SEALED
    if is_sealed:
        condition_code = BuylistItem.CONDITION_SEALED

    variants = card.get('variants') or []
    variant = _pick_variant(variants, condition_code, printing=printing)
    if not variant:
        label = dict(BuylistItem.CONDITION_CHOICES).get(condition_code, condition_code)
        raise JustTCGPriceMissingError(
            f'No {label} pricing found for this product.'
        )

    price = _parse_price(variant.get('price'))
    if price is None:
        label = dict(BuylistItem.CONDITION_CHOICES).get(condition_code, condition_code)
        raise JustTCGPriceMissingError(
            f'Price is missing for {label} '
            f'({variant.get("printing") or "unknown printing"}).'
        )

    return {
        'card_id': card.get('id') or card_id,
        'card_name': card.get('name') or '',
        'set_name': card.get('set_name') or card.get('set') or '',
        'game': card.get('game') or '',
        'number': str(card.get('number') or ''),
        'rarity': card.get('rarity') or '',
        'tcgplayerId': str(card.get('tcgplayerId') or ''),
        'condition': condition_code,
        'printing': variant.get('printing') or '',
        'price': price,
        'is_sealed': is_sealed,
    }
