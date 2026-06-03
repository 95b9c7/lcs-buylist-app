import csv
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    BuylistForm,
    BuylistItemForm,
    BuylistPaymentChoiceForm,
    BuylistStatusForm,
    BuylistUnlockForm,
    CustomerForm,
    PricingRuleForm,
)
from .activity import log_buylist_activity
from .models import Buylist, BuylistActivity, BuylistItem, Customer, PricingRule, round_money
from .services.justtcg import (
    JustTCGKeyMissingError,
    JustTCGPriceMissingError,
    JustTCGRequestError,
    get_condition_price,
    search_cards,
)
from .buylist_locking import (
    can_edit_buylist_items,
    can_unlock_buylist,
    lock_status_message,
    show_locked_badge,
)
from .permissions import (
    employee_required,
    manager_or_owner_required,
    owner_required,
    user_is_manager_or_owner,
    user_is_owner,
)
from django.core.exceptions import PermissionDenied


def permission_denied_view(request, exception):
    return render(request, 'buylists/403.html', status=403)


def _check_can_edit_items(buylist, user):
    if not can_edit_buylist_items(buylist, user):
        raise PermissionDenied(lock_status_message(buylist, user))


def _line_market_value_expression():
    return ExpressionWrapper(
        F('quantity') * F('market_price'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )


def _money_zero():
    return Value(
        Decimal('0.00'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )


def _owner_dashboard_context():
    """Aggregate metrics for the owner dashboard section."""
    line_market = _line_market_value_expression()
    money_zero = _money_zero()

    item_totals = BuylistItem.objects.aggregate(
        total_market=Coalesce(Sum(line_market), money_zero),
        total_offer=Coalesce(Sum('final_offer_price'), money_zero),
    )
    accepted_offer = BuylistItem.objects.filter(
        buylist__status=Buylist.STATUS_ACCEPTED,
    ).aggregate(
        total=Coalesce(Sum('final_offer_price'), money_zero),
    )
    paid_total = Buylist.objects.filter(
        status=Buylist.STATUS_PAID,
    ).aggregate(
        total=Coalesce(Sum('amount_paid'), money_zero),
    )

    total_market_value = round_money(item_totals['total_market'])
    total_offer_value = round_money(item_totals['total_offer'])
    total_accepted_offer_value = round_money(accepted_offer['total'])
    total_paid_amount = round_money(paid_total['total'])

    average_offer_percent = None
    if total_market_value > 0:
        average_offer_percent = round(
            float(total_offer_value / total_market_value * 100),
            1,
        )

    now = timezone.now()
    week_start = now.replace(
        hour=0, minute=0, second=0, microsecond=0,
    ) - timedelta(days=now.weekday())

    buylist_stats = Buylist.objects.aggregate(
        total_buylists=Count('id'),
        buylists_this_week=Count('id', filter=Q(created_at__gte=week_start)),
    )

    status_counts = {
        row['status']: row['count']
        for row in Buylist.objects.values('status').annotate(count=Count('id'))
    }
    status_breakdown = [
        {
            'status': value,
            'label': label,
            'count': status_counts.get(value, 0),
        }
        for value, label in Buylist.STATUS_CHOICES
    ]

    recent_buylists = (
        Buylist.objects.select_related('customer')
        .prefetch_related('items')
        .order_by('-updated_at')[:10]
    )

    return {
        'owner_metrics': {
            'total_buylists': buylist_stats['total_buylists'],
            'buylists_this_week': buylist_stats['buylists_this_week'],
            'total_market_value': total_market_value,
            'total_offer_value': total_offer_value,
            'total_accepted_offer_value': total_accepted_offer_value,
            'total_paid_amount': total_paid_amount,
            'average_offer_percent': average_offer_percent,
        },
        'status_breakdown': status_breakdown,
        'recent_buylists': recent_buylists,
    }


@employee_required
def dashboard(request):
    buylists = (
        Buylist.objects.select_related('customer')
        .prefetch_related('items')
        .order_by('-created_at')
    )

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if search_query:
        buylists = buylists.filter(customer__name__icontains=search_query)

    if status_filter:
        buylists = buylists.filter(status=status_filter)

    buylists = buylists[:50]

    context = {
        'buylists': buylists,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Buylist.STATUS_CHOICES,
        'show_owner_metrics': user_is_owner(request.user),
    }
    if context['show_owner_metrics']:
        context.update(_owner_dashboard_context())

    return render(request, 'buylists/dashboard.html', context)


@employee_required
def customer_list(request):
    customers = (
        Customer.objects.annotate(
            buylist_count=Count('buylists', distinct=True),
            total_offered=Coalesce(
                Sum('buylists__items__final_offer_price'),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .order_by('name')
    )

    search_query = request.GET.get('q', '').strip()
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query)
            | Q(phone__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    for customer in customers:
        customer.total_offered = round_money(customer.total_offered)

    return render(request, 'buylists/customer_list.html', {
        'customers': customers,
        'search_query': search_query,
    })


@employee_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    buylists = (
        Buylist.objects.filter(customer=customer)
        .prefetch_related('items')
        .order_by('-created_at')
    )
    total_offered = round_money(
        sum(buylist.total_final_offer_value for buylist in buylists)
    )
    return render(request, 'buylists/customer_detail.html', {
        'customer': customer,
        'buylists': buylists,
        'total_offered': total_offered,
    })


@employee_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Customer "{customer.name}" created.')
            return redirect('buylists:customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()
    return render(request, 'buylists/customer_form.html', {
        'form': form,
        'title': 'New Customer',
    })


@employee_required
def buylist_create(request):
    customer = None
    customer_pk = request.GET.get('customer')
    if customer_pk:
        customer = get_object_or_404(Customer, pk=customer_pk)

    if request.method == 'POST':
        form = BuylistForm(request.POST, user=request.user)
        if form.is_valid():
            buylist = form.save(commit=False)
            if request.user.is_authenticated:
                buylist.created_by = request.user
                if buylist.status in Buylist.TERMINAL_STATUSES:
                    buylist.completed_by = request.user
                    buylist.completed_at = timezone.now()
            buylist.save()
            messages.success(request, 'Buylist created.')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        initial = {'customer': customer} if customer else None
        form = BuylistForm(initial=initial, user=request.user)

    return render(request, 'buylists/buylist_form.html', {
        'form': form,
        'title': 'New Buylist',
        'customer': customer,
    })


@employee_required
def buylist_detail(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related(
            'customer', 'created_by', 'completed_by', 'paid_by', 'unlocked_by',
        ).prefetch_related(
            'items__override_by',
            'activities__user',
        ),
        pk=pk,
    )
    activities = buylist.activities.all()
    can_manage_settings = user_is_manager_or_owner(request.user)
    can_edit_items = can_edit_buylist_items(buylist, request.user)
    status_form = (
        BuylistStatusForm(instance=buylist, user=request.user)
        if can_manage_settings else None
    )
    payment_form = BuylistPaymentChoiceForm(instance=buylist) if can_manage_settings else None
    unlock_form = (
        BuylistUnlockForm()
        if can_unlock_buylist(buylist, request.user) else None
    )
    return render(request, 'buylists/buylist_detail.html', {
        'buylist': buylist,
        'status_form': status_form,
        'payment_form': payment_form,
        'unlock_form': unlock_form,
        'can_manage_settings': can_manage_settings,
        'can_edit_items': can_edit_items,
        'show_locked_badge': show_locked_badge(buylist, request.user),
        'lock_message': lock_status_message(buylist, request.user),
        'override_item_count': buylist.override_item_count,
        'activities': activities,
    })


@employee_required
def buylist_export_csv(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    safe_customer_name = re.sub(
        r'[^\w\-_]',
        '',
        buylist.customer.name.replace(' ', '_'),
    ) or 'customer'
    filename = f'buylist_{buylist.pk}_customer_{safe_customer_name}.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Buylist ID',
        'Customer Name',
        'Card Name',
        'Set Name',
        'Quantity',
        'Condition',
        'Market Price',
        'Offer Percent',
        'Recommended Offer Price',
        'Final Offer Price',
        'Override Reason',
        'Override Recommended',
        'Override Final',
        'Override By',
        'Override At',
        'Notes',
    ])

    for item in buylist.items.all():
        if item.offer_percent is not None:
            offer_percent = int(item.offer_percent * 100)
        else:
            offer_percent = ''
        writer.writerow([
            buylist.pk,
            buylist.customer.name,
            item.card_name,
            item.set_name,
            item.quantity,
            item.condition,
            item.market_price,
            offer_percent,
            item.recommended_offer_price,
            item.final_offer_price,
            item.override_reason,
            item.override_recommended_price,
            item.override_final_price,
            item.override_by.username if item.override_by else '',
            item.override_at,
            item.notes,
        ])

    log_buylist_activity(
        buylist,
        request.user,
        BuylistActivity.ACTION_CSV_EXPORTED,
        f'Exported buylist #{buylist.pk} to CSV.',
    )
    return response


@employee_required
def buylist_offer_sheet(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer', 'paid_by').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    log_buylist_activity(
        buylist,
        request.user,
        BuylistActivity.ACTION_OFFER_PRINTED,
        f'Viewed offer sheet for buylist #{buylist.pk}.',
    )
    return render(request, 'buylists/buylist_offer_sheet.html', {
        'buylist': buylist,
        'store_name': '[Your Store Name]',
    })


@manager_or_owner_required
@require_POST
def buylist_update_status(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    old_status = buylist.status
    form = BuylistStatusForm(request.POST, instance=buylist, user=request.user)
    if form.is_valid():
        buylist = form.save()
        if old_status != buylist.status:
            old_label = dict(Buylist.STATUS_CHOICES).get(old_status, old_status)
            log_buylist_activity(
                buylist,
                request.user,
                BuylistActivity.ACTION_STATUS_CHANGED,
                f'Status changed from {old_label} to {buylist.get_status_display()}.',
            )
        if buylist.is_paid:
            log_buylist_activity(
                buylist,
                request.user,
                BuylistActivity.ACTION_PAYMENT_RECORDED,
                (
                    f'Payment recorded: ${buylist.amount_paid} via '
                    f'{buylist.get_payment_method_display()}.'
                ),
            )
        if buylist.is_paid:
            messages.success(
                request,
                f'Buylist marked Paid — ${buylist.amount_paid} via '
                f'{buylist.get_payment_method_display()}.',
            )
        else:
            messages.success(request, f'Status updated to {buylist.get_status_display()}.')
    else:
        messages.error(request, 'Could not update status. Check payment fields if marking Paid.')
    return redirect('buylists:buylist_detail', pk=pk)


@owner_required
@require_POST
def buylist_unlock_items(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    if not can_unlock_buylist(buylist, request.user):
        raise PermissionDenied('Only an Owner can unlock this buylist.')

    form = BuylistUnlockForm(request.POST)
    if form.is_valid():
        buylist.unlock_reason = form.cleaned_data['unlock_reason']
        buylist.unlocked_by = request.user
        buylist.unlocked_at = timezone.now()
        buylist.save()
        messages.success(request, 'Buylist unlocked for item editing.')
    else:
        messages.error(request, 'Unlock reason is required.')
    return redirect('buylists:buylist_detail', pk=pk)


@manager_or_owner_required
@require_POST
def buylist_update_payment_choice(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    old_payment_choice = buylist.payment_choice
    form = BuylistPaymentChoiceForm(request.POST, instance=buylist)
    if form.is_valid():
        buylist = form.save()
        payment_changed = old_payment_choice != buylist.payment_choice
        buylist.recalculate_offer_allocations(
            override_user=request.user,
            reset_final_offers=payment_changed,
        )
        if buylist.payment_choice:
            label = buylist.get_payment_choice_display()
            if payment_changed:
                messages.success(
                    request,
                    f'Payment choice set to {label}. Final offers updated to match.',
                )
            else:
                messages.success(request, f'Payment choice set to {label}.')
        else:
            if payment_changed:
                messages.success(
                    request,
                    'Payment choice cleared. Final offers updated to match.',
                )
            else:
                messages.success(request, 'Payment choice cleared.')
    else:
        messages.error(request, 'Could not update payment choice.')
    return redirect('buylists:buylist_detail', pk=pk)


def _card_search_initial(request):
    """Build form initial data from JustTCG card selection query params."""
    initial = {}
    card_name = request.GET.get('card_name', '').strip()
    set_name = request.GET.get('set_name', '').strip()
    market_price = request.GET.get('market_price', '').strip()
    condition = request.GET.get('condition', '').strip()

    if card_name:
        initial['card_name'] = card_name
    if set_name:
        initial['set_name'] = set_name
    if market_price:
        try:
            initial['market_price'] = Decimal(market_price)
        except (InvalidOperation, TypeError):
            pass
    if condition:
        initial['condition'] = condition
    if request.GET.get('priced') == '1':
        # JustTCG market_price already reflects the selected condition.
        initial['condition_percent'] = Decimal('1.00')

    return initial


def _pricing_error_context(exc):
    if isinstance(exc, JustTCGKeyMissingError):
        return (
            'missing_key',
            'JUSTTCG_API_KEY is not set. Add your API key to .env and restart the server.',
        )
    if isinstance(exc, JustTCGPriceMissingError):
        return 'missing_price', str(exc)
    if isinstance(exc, JustTCGRequestError):
        return 'request_failed', str(exc)
    return 'request_failed', str(exc)


@employee_required
def buylist_card_search(request, buylist_pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    _check_can_edit_items(buylist, request.user)

    query = request.GET.get('q', '').strip()
    game = request.GET.get('game', 'pokemon').strip() or 'pokemon'
    product_type = request.GET.get('product_type', 'singles').strip() or 'singles'
    results = []
    error_type = None
    error_message = None

    if query:
        try:
            results = search_cards(query, game=game, product_type=product_type)
            if not results:
                error_type = 'no_results'
                error_message = f'No cards found for "{query}". Try a different name.'
        except JustTCGKeyMissingError as exc:
            error_type, error_message = _pricing_error_context(exc)
        except JustTCGRequestError as exc:
            error_type, error_message = _pricing_error_context(exc)

    return render(request, 'buylists/buylist_card_search.html', {
        'buylist': buylist,
        'query': query,
        'game': game,
        'product_type': product_type,
        'product_type_choices': [
            ('singles', 'Singles'),
            ('sealed', 'Sealed product'),
            ('all', 'All'),
        ],
        'results': results,
        'error_type': error_type,
        'error_message': error_message,
    })


@employee_required
def buylist_card_condition(request, buylist_pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    _check_can_edit_items(buylist, request.user)

    card = {
        'id': request.GET.get('card_id', request.POST.get('card_id', '')).strip(),
        'name': request.GET.get('card_name', request.POST.get('card_name', '')).strip(),
        'game': request.GET.get('game', request.POST.get('game', '')).strip(),
        'set': request.GET.get('set_name', request.POST.get('set_name', '')).strip(),
        'number': request.GET.get('number', request.POST.get('number', '')).strip(),
        'rarity': request.GET.get('rarity', request.POST.get('rarity', '')).strip(),
        'tcgplayerId': request.GET.get(
            'tcgplayer_id', request.POST.get('tcgplayer_id', ''),
        ).strip(),
        'is_sealed': (
            request.GET.get('is_sealed', request.POST.get('is_sealed', '')).lower()
            in ('1', 'true', 'yes')
        ),
    }
    error_type = None
    error_message = None
    if card['is_sealed']:
        selected_condition = BuylistItem.CONDITION_SEALED
    else:
        selected_condition = BuylistItem.CONDITION_NM
    selected_printing = ''

    if not card['id']:
        error_type = 'request_failed'
        error_message = 'No card was selected. Search again and pick a card.'

    if request.method == 'POST' and card['id']:
        selected_condition = request.POST.get(
            'condition',
            BuylistItem.CONDITION_SEALED if card['is_sealed'] else BuylistItem.CONDITION_NM,
        )
        selected_printing = request.POST.get('printing', '').strip()
        try:
            price_info = get_condition_price(
                card['id'],
                selected_condition,
                printing=selected_printing or None,
            )
            params = {
                'card_name': price_info['card_name'],
                'set_name': price_info['set_name'],
                'market_price': str(price_info['price']),
                'condition': price_info['condition'],
                'priced': '1',
            }
            if price_info.get('is_sealed'):
                params['is_sealed'] = '1'
            create_url = reverse(
                'buylists:buylistitem_create',
                kwargs={'buylist_pk': buylist.pk},
            )
            return redirect(f'{create_url}?{urlencode(params)}')
        except JustTCGKeyMissingError as exc:
            error_type, error_message = _pricing_error_context(exc)
        except JustTCGPriceMissingError as exc:
            error_type, error_message = _pricing_error_context(exc)
        except JustTCGRequestError as exc:
            error_type, error_message = _pricing_error_context(exc)

    return render(request, 'buylists/buylist_card_condition.html', {
        'buylist': buylist,
        'card': card,
        'condition_choices': BuylistItem.condition_choices_for_product(
            card['is_sealed'],
        ),
        'selected_condition': selected_condition,
        'selected_printing': selected_printing,
        'printing_choices': ['Normal', 'Foil'],
        'error_type': error_type,
        'error_message': error_message,
    })


@employee_required
def buylistitem_create(request, buylist_pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    _check_can_edit_items(buylist, request.user)
    if request.method == 'POST':
        form = BuylistItemForm(request.POST, buylist=buylist, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.buylist = buylist
            item.save(override_user=request.user)
            log_buylist_activity(
                buylist,
                request.user,
                BuylistActivity.ACTION_ITEM_ADDED,
                f'Added "{item.card_name}" (qty {item.quantity}).',
            )
            messages.success(request, f'Added "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        search_initial = _card_search_initial(request)
        form = BuylistItemForm(
            buylist=buylist,
            user=request.user,
            initial=search_initial or None,
        )
    search_initial = _card_search_initial(request) if request.method != 'POST' else {}
    price_missing = (
        request.GET.get('price_missing') == '1'
        or (
            request.method != 'POST'
            and search_initial
            and 'market_price' not in search_initial
        )
    )
    return render(request, 'buylists/buylistitem_form.html', {
        'form': form,
        'buylist': buylist,
        'title': 'Add Card',
        'from_card_search': bool(search_initial),
        'justtcg_priced': request.GET.get('priced') == '1',
        'price_missing': price_missing,
    })


@employee_required
def buylistitem_edit(request, buylist_pk, pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    _check_can_edit_items(buylist, request.user)
    item = get_object_or_404(BuylistItem, pk=pk, buylist=buylist)
    if request.method == 'POST':
        had_override = bool(item.override_at)
        form = BuylistItemForm(
            request.POST, instance=item, buylist=buylist, user=request.user,
        )
        if form.is_valid():
            item = form.save()
            log_buylist_activity(
                buylist,
                request.user,
                BuylistActivity.ACTION_ITEM_UPDATED,
                f'Updated "{item.card_name}".',
            )
            if item.is_offer_overridden and not had_override:
                log_buylist_activity(
                    buylist,
                    request.user,
                    BuylistActivity.ACTION_OVERRIDE_ADDED,
                    (
                        f'Override on "{item.card_name}": '
                        f'${item.recommended_offer_price} → ${item.final_offer_price} '
                        f'({item.override_reason}).'
                    ),
                )
            messages.success(request, f'Updated "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistItemForm(instance=item, buylist=buylist, user=request.user)
    return render(request, 'buylists/buylistitem_form.html', {
        'form': form,
        'buylist': buylist,
        'title': 'Edit Card',
        'item': item,
    })


@employee_required
def buylistitem_delete(request, buylist_pk, pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    _check_can_edit_items(buylist, request.user)
    item = get_object_or_404(BuylistItem, pk=pk, buylist=buylist)
    if request.method == 'POST':
        card_name = item.card_name
        item.delete()
        buylist.recalculate_offer_allocations(override_user=request.user)
        log_buylist_activity(
            buylist,
            request.user,
            BuylistActivity.ACTION_ITEM_DELETED,
            f'Removed "{card_name}".',
        )
        messages.success(request, f'Removed "{card_name}".')
        return redirect('buylists:buylist_detail', pk=buylist.pk)
    return render(request, 'buylists/buylistitem_confirm_delete.html', {
        'buylist': buylist,
        'item': item,
    })


REPORT_PERIOD_TODAY = 'today'
REPORT_PERIOD_WEEK = 'week'
REPORT_PERIOD_MONTH = 'month'
REPORT_PERIOD_CUSTOM = 'custom'

REPORT_PERIOD_CHOICES = [
    (REPORT_PERIOD_TODAY, 'Today'),
    (REPORT_PERIOD_WEEK, 'This Week'),
    (REPORT_PERIOD_MONTH, 'This Month'),
    (REPORT_PERIOD_CUSTOM, 'Custom'),
]


def _parse_report_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def _report_date_range(request):
    today = timezone.localdate()
    period = request.GET.get('period', REPORT_PERIOD_TODAY).strip()
    if period not in {choice[0] for choice in REPORT_PERIOD_CHOICES}:
        period = REPORT_PERIOD_TODAY

    if period == REPORT_PERIOD_WEEK:
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == REPORT_PERIOD_MONTH:
        start_date = today.replace(day=1)
        end_date = today
    elif period == REPORT_PERIOD_CUSTOM:
        start_date = _parse_report_date(request.GET.get('start_date'), today)
        end_date = _parse_report_date(request.GET.get('end_date'), start_date)
        if end_date < start_date:
            end_date = start_date
    else:
        start_date = today
        end_date = today

    start_at = timezone.make_aware(datetime.combine(start_date, time.min))
    end_at = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
    )
    if start_date == end_date:
        range_label = start_date.strftime('%b %-d, %Y')
    else:
        range_label = (
            f'{start_date.strftime("%b %-d, %Y")} - '
            f'{end_date.strftime("%b %-d, %Y")}'
        )

    return {
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'start_at': start_at,
        'end_at': end_at,
        'range_label': range_label,
    }


def _report_money_total(values):
    return round_money(sum(values, Decimal('0.00')))


def _buylist_report_summary(buylists):
    return {
        'total_buylists': len(buylists),
        'total_market_value': _report_money_total(
            buylist.total_market_value for buylist in buylists
        ),
        'total_offer_value': _report_money_total(
            buylist.total_offer_value for buylist in buylists
        ),
        'total_paid_amount': _report_money_total(
            buylist.amount_paid or Decimal('0.00') for buylist in buylists
        ),
        'accepted_count': sum(
            1 for buylist in buylists if buylist.status == Buylist.STATUS_ACCEPTED
        ),
        'rejected_count': sum(
            1 for buylist in buylists if buylist.status == Buylist.STATUS_REJECTED
        ),
        'paid_count': sum(
            1 for buylist in buylists if buylist.status == Buylist.STATUS_PAID
        ),
    }


def _employee_options():
    User = get_user_model()
    return User.objects.filter(is_active=True).order_by('username')


def _employee_breakdown(buylists, employee_options):
    rows = []
    for employee in employee_options:
        created = [
            buylist for buylist in buylists
            if buylist.created_by_id == employee.pk
        ]
        completed = [
            buylist for buylist in buylists
            if buylist.completed_by_id == employee.pk
        ]
        if not created and not completed:
            continue

        rows.append({
            'employee': employee,
            'created_count': len(created),
            'completed_count': len(completed),
            'total_offer_value': _report_money_total(
                buylist.total_offer_value for buylist in completed
            ),
            'total_paid_amount': _report_money_total(
                buylist.amount_paid or Decimal('0.00') for buylist in completed
            ),
            'accepted_count': sum(
                1 for buylist in completed
                if buylist.status == Buylist.STATUS_ACCEPTED
            ),
            'rejected_count': sum(
                1 for buylist in completed
                if buylist.status == Buylist.STATUS_REJECTED
            ),
            'paid_count': sum(
                1 for buylist in completed
                if buylist.status == Buylist.STATUS_PAID
            ),
        })
    return rows


@employee_required
def buylist_report(request):
    date_range = _report_date_range(request)
    can_view_all_employees = user_is_manager_or_owner(request.user)
    if can_view_all_employees:
        employee_options = list(_employee_options())
    else:
        employee_options = [request.user]
    selected_employee_id = request.GET.get('employee', '').strip()
    selected_employee = None

    if can_view_all_employees and selected_employee_id:
        try:
            selected_employee = get_user_model().objects.get(
                pk=int(selected_employee_id),
                is_active=True,
            )
        except (ValueError, get_user_model().DoesNotExist):
            selected_employee_id = ''
            selected_employee = None
    elif not can_view_all_employees:
        selected_employee = request.user
        selected_employee_id = str(request.user.pk)

    status_filter = request.GET.get('status', '').strip()
    valid_statuses = {status for status, _label in Buylist.STATUS_CHOICES}
    if status_filter not in valid_statuses:
        status_filter = ''

    buylists = (
        Buylist.objects.select_related(
            'customer', 'created_by', 'completed_by', 'paid_by',
        )
        .prefetch_related('items')
        .filter(
            Q(created_at__gte=date_range['start_at'], created_at__lt=date_range['end_at'])
            | Q(
                completed_at__gte=date_range['start_at'],
                completed_at__lt=date_range['end_at'],
            )
        )
        .order_by('-created_at', '-pk')
    )

    if status_filter:
        buylists = buylists.filter(status=status_filter)

    if selected_employee:
        buylists = buylists.filter(
            Q(created_by=selected_employee) | Q(completed_by=selected_employee),
        )

    buylists = list(buylists)
    summary = _buylist_report_summary(buylists)
    employee_breakdown = _employee_breakdown(buylists, employee_options)
    status_labels = dict(Buylist.STATUS_CHOICES)

    if selected_employee:
        employee_filter_label = selected_employee.get_username()
    else:
        employee_filter_label = 'All employees'

    return render(request, 'buylists/buylist_report.html', {
        'buylists': buylists,
        'summary': summary,
        'employee_breakdown': employee_breakdown,
        'period_choices': REPORT_PERIOD_CHOICES,
        'selected_period': date_range['period'],
        'start_date': date_range['start_date'],
        'end_date': date_range['end_date'],
        'range_label': date_range['range_label'],
        'status_choices': Buylist.STATUS_CHOICES,
        'status_filter': status_filter,
        'status_filter_label': status_labels.get(status_filter, 'All'),
        'employee_options': employee_options,
        'selected_employee_id': selected_employee_id,
        'employee_filter_label': employee_filter_label,
        'can_view_all_employees': can_view_all_employees,
    })


@manager_or_owner_required
def paid_report(request):
    paid_buylists = (
        Buylist.objects.filter(status=Buylist.STATUS_PAID)
        .select_related('customer', 'paid_by')
        .prefetch_related('items')
        .order_by('-paid_at')
    )
    total_paid = round_money(
        sum(b.amount_paid for b in paid_buylists if b.amount_paid is not None)
    )
    return render(request, 'buylists/paid_report.html', {
        'paid_buylists': paid_buylists,
        'total_paid': total_paid,
    })


@manager_or_owner_required
def override_report(request):
    overrides = (
        BuylistItem.objects.filter(override_at__isnull=False)
        .select_related('buylist__customer', 'override_by')
        .order_by('-override_at')
    )
    total_extra = round_money(
        sum(item.override_difference for item in overrides)
    )
    return render(request, 'buylists/override_report.html', {
        'overrides': overrides,
        'total_extra': total_extra,
    })


@owner_required
def pricing_rule_list(request):
    rules = PricingRule.objects.all()
    return render(request, 'buylists/pricing_rule_list.html', {
        'rules': rules,
    })


@owner_required
def pricing_rule_create(request):
    if request.method == 'POST':
        form = PricingRuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pricing rule created.')
            return redirect('buylists:pricing_rule_list')
    else:
        form = PricingRuleForm()
    return render(request, 'buylists/pricing_rule_form.html', {
        'form': form,
        'title': 'New Pricing Rule',
    })


@owner_required
def pricing_rule_edit(request, pk):
    rule = get_object_or_404(PricingRule, pk=pk)
    if request.method == 'POST':
        form = PricingRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pricing rule updated.')
            return redirect('buylists:pricing_rule_list')
    else:
        form = PricingRuleForm(instance=rule)
    return render(request, 'buylists/pricing_rule_form.html', {
        'form': form,
        'title': 'Edit Pricing Rule',
        'rule': rule,
    })
