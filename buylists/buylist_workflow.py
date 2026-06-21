"""Buylist status progression and which settings appear at each phase."""

from .models import Buylist

# Allowed forward/back actions shown as buttons (not every status in a dropdown).
STATUS_ACTIONS = {
    Buylist.STATUS_DRAFT: [
        {
            'status': Buylist.STATUS_WAITING,
            'label': 'Send to Waiting',
            'variant': 'primary',
        },
    ],
    Buylist.STATUS_WAITING: [
        {
            'status': Buylist.STATUS_ACCEPTED,
            'label': 'Mark Accepted',
            'variant': 'success',
        },
        {
            'status': Buylist.STATUS_REJECTED,
            'label': 'Reject',
            'variant': 'outline-danger',
        },
        {
            'status': Buylist.STATUS_DRAFT,
            'label': 'Back to Draft',
            'variant': 'outline-secondary',
        },
    ],
    Buylist.STATUS_ACCEPTED: [
        {
            'status': Buylist.STATUS_REJECTED,
            'label': 'Reject',
            'variant': 'outline-danger',
        },
        {
            'status': Buylist.STATUS_WAITING,
            'label': 'Back to Waiting',
            'variant': 'outline-secondary',
        },
    ],
    Buylist.STATUS_REJECTED: [
        {
            'status': Buylist.STATUS_DRAFT,
            'label': 'Reopen as Draft',
            'variant': 'outline-secondary',
        },
    ],
    Buylist.STATUS_PAID: [],
}


def get_status_actions(buylist):
    return STATUS_ACTIONS.get(buylist.status, [])


def is_allowed_status_change(current_status, new_status):
    allowed = {action['status'] for action in STATUS_ACTIONS.get(current_status, [])}
    return new_status in allowed


def show_payment_choice_settings(buylist):
    """Customer cash/trade rate — only after the offer is accepted."""
    return buylist.status in {
        Buylist.STATUS_ACCEPTED,
        Buylist.STATUS_PAID,
    }


def show_mark_paid_form(buylist):
    """Store payment method and amount — only while Accepted."""
    return buylist.status == Buylist.STATUS_ACCEPTED


def show_payment_recorded(buylist):
    return buylist.status == Buylist.STATUS_PAID
