from .models import BuylistActivity


def log_buylist_activity(buylist, user, action, description):
    """Record one event on a buylist activity timeline."""
    BuylistActivity.objects.create(
        buylist=buylist,
        user=user if user and user.is_authenticated else None,
        action=action,
        description=description,
    )
