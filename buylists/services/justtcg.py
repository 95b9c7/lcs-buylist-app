from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from ..models import BuylistItem, round_money

BASE_URL = 'https://api.justtcg.com/v1'
DEFAULT_TIMEOUT = 15
# Free/starter JustTCG plans allow at most 20 results per request.
SEARCH_RESULT_LIMIT = 20

GAME_SLUG_TO_NAME = {
    'pokemon': 'Pokemon',
    'magic': 'Magic: The Gathering',
    'yugioh': 'Yu-Gi-Oh!',
    'lorcana': 'Disney Lorcana',
    'onepiece': 'One Piece TCG',
}

CONDITION_NAME_TO_CODE = {
    'near mint': 'NM',
    'nm': 'NM',
    'lightly played': 'LP',
    'lp': 'LP',
    'moderately played': 'MP',
    'mp': 'MP',
    'heavily played': 'HP',
    'hp': 'HP',
    'damaged': 'DMG',
    'dmg': 'DMG',
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
    if code.upper() in dict(BuylistItem.CONDITION_CHOICES):
        return code.upper()
    mapped = CONDITION_NAME_TO_CODE.get(code.lower())
    if mapped:
        return mapped
    return BuylistItem.CONDITION_NM


def _condition_matches(variant_condition, condition_code):
    variant_code = CONDITION_NAME_TO_CODE.get(
        (variant_condition or '').strip().lower(),
        (variant_condition or '').strip().upper(),
    )
    return variant_code == condition_code


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

    return {
        'id': raw.get('id') or '',
        'name': raw.get('name') or '',
        'game': raw.get('game') or '',
        'set': set_name,
        'number': str(raw.get('number') or ''),
        'rarity': raw.get('rarity') or '',
        'tcgplayerId': str(tcgplayer_id) if tcgplayer_id else '',
    }


def search_cards(query, game=None):
    """
    Search JustTCG for cards by name.

    Returns a list of dicts with id, name, game, set, number, rarity, tcgplayerId.
    """
    query = (query or '').strip()
    if not query:
        return []

    params = {'q': query, 'limit': SEARCH_RESULT_LIMIT}
    if game:
        params['game'] = GAME_SLUG_TO_NAME.get(game, game)

    payload = _api_get('cards', params)
    results = []
    for raw in _extract_data(payload):
        if isinstance(raw, dict):
            card = _normalize_search_card(raw)
            if card['name']:
                results.append(card)
    return results


def _pick_variant(variants, condition_code, printing=None):
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

    if not printing:
        for variant in matches:
            if (variant.get('printing') or '').strip().lower() == 'normal':
                return variant

    priced = [variant for variant in matches if _parse_price(variant.get('price')) is not None]
    if priced:
        return min(
            priced,
            key=lambda variant: _parse_price(variant.get('price')),
        )
    return matches[0]


def get_condition_price(card_id, condition, printing=None):
    """
    Fetch the market price for a card in a specific condition.

    Returns card_name, set_name, condition, printing, and price.
    """
    card_id = (card_id or '').strip()
    if not card_id:
        raise JustTCGRequestError('A card id is required to look up pricing.')

    condition_code = _normalize_condition_code(condition)
    params = {
        'cardId': card_id,
        'condition': condition_code,
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
    variants = card.get('variants') or []
    variant = _pick_variant(variants, condition_code, printing=printing)
    if not variant:
        raise JustTCGPriceMissingError(
            f'No {condition_code} pricing found for this card.'
        )

    price = _parse_price(variant.get('price'))
    if price is None:
        raise JustTCGPriceMissingError(
            f'Price is missing for {condition_code} '
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
    }
