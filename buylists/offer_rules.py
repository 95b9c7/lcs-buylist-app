from decimal import Decimal

from .models import round_money

from .permissions import GROUP_MANAGER, GROUP_OWNER

GROUP_ADMIN = 'Admin'  # legacy; treated like Owner for overrides

EMPLOYEE_MAX_OVERRIDE_PERCENT = Decimal('5')
MANAGER_MAX_OVERRIDE_PERCENT = Decimal('15')


def get_override_limit_percent(user):
    """
    Return max percent above recommended, or None for unlimited.
    Uses Django groups: Manager (15%), Owner/Admin (unlimited), else Employee (5%).
    Superusers are unlimited.
    """
    if not user or not user.is_authenticated:
        return EMPLOYEE_MAX_OVERRIDE_PERCENT

    if user.is_superuser:
        return None

    group_names = set(user.groups.values_list('name', flat=True))

    if GROUP_OWNER in group_names or GROUP_ADMIN in group_names:
        return None

    if GROUP_MANAGER in group_names:
        return MANAGER_MAX_OVERRIDE_PERCENT

    return EMPLOYEE_MAX_OVERRIDE_PERCENT


def get_role_label(user):
    limit = get_override_limit_percent(user)
    if limit is None:
        return 'Owner (unlimited override)'
    if limit == MANAGER_MAX_OVERRIDE_PERCENT:
        return 'Manager (up to 15% above recommended)'
    return 'Employee (up to 5% above recommended)'


def max_allowed_final_offer(recommended, user):
    limit_percent = get_override_limit_percent(user)
    if limit_percent is None:
        return None
    multiplier = Decimal('1') + (limit_percent / Decimal('100'))
    return round_money(recommended * multiplier)


def validate_final_offer(user, recommended, final, override_reason):
    errors = []

    if final > recommended and not (override_reason or '').strip():
        errors.append(
            'Override reason is required when final offer is above recommended.'
        )

    max_allowed = max_allowed_final_offer(recommended, user)
    if max_allowed is not None and final > max_allowed:
        limit = get_override_limit_percent(user)
        errors.append(
            f'Final offer cannot exceed ${max_allowed} '
            f'({limit}% above recommended) for your role.'
        )

    return errors
