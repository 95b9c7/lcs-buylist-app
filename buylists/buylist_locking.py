from .permissions import user_is_manager_or_owner, user_is_owner


def can_edit_buylist_items(buylist, user):
    """
    Whether the user may add, edit, or delete cards on this buylist.

    - Draft: all staff
    - Waiting: Manager or Owner only
    - Accepted: only while unlocked (any staff); Owner unlocks first
    - Paid: Owner only
    - Rejected: Manager or Owner only
    """
    if not user.is_authenticated:
        return False

    if user_is_owner(user):
        return True

    status = buylist.status

    if status == buylist.STATUS_DRAFT:
        return True

    if status == buylist.STATUS_WAITING:
        return user_is_manager_or_owner(user)

    if status == buylist.STATUS_ACCEPTED:
        return bool(buylist.unlocked_at)

    if status == buylist.STATUS_PAID:
        return False

    if status == buylist.STATUS_REJECTED:
        return user_is_manager_or_owner(user)

    return False


def show_locked_badge(buylist, user):
    """Show locked badge when items cannot be edited by this user."""
    return not can_edit_buylist_items(buylist, user)


def lock_status_message(buylist, user):
    if can_edit_buylist_items(buylist, user):
        return ''

    if buylist.status == buylist.STATUS_WAITING:
        return 'Waiting buylists can only be edited by a Manager or Owner.'

    if buylist.status == buylist.STATUS_ACCEPTED and not buylist.unlocked_at:
        return (
            'Accepted buylists are locked until an Owner unlocks them '
            'for editing.'
        )

    if buylist.status == buylist.STATUS_PAID:
        if user_is_owner(user):
            return ''
        return 'Paid buylists are locked. Only an Owner may edit cards.'

    if buylist.status == buylist.STATUS_REJECTED:
        return 'Rejected buylists can only be edited by a Manager or Owner.'

    return 'This buylist is locked for editing.'


def can_unlock_buylist(buylist, user):
    """Owner may unlock Accepted buylists that are still locked."""
    return (
        user_is_owner(user)
        and buylist.status == buylist.STATUS_ACCEPTED
        and not buylist.unlocked_at
    )
