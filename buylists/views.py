import csv
import re
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    BuylistForm,
    BuylistItemForm,
    BuylistPaymentChoiceForm,
    BuylistStatusForm,
    CustomerForm,
    PricingRuleForm,
)
from .models import Buylist, BuylistItem, Customer, PricingRule, round_money
from .permissions import (
    employee_required,
    manager_or_owner_required,
    owner_required,
    user_is_manager_or_owner,
)


def permission_denied_view(request, exception):
    return render(request, 'buylists/403.html', status=403)


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

    return render(request, 'buylists/dashboard.html', {
        'buylists': buylists,
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Buylist.STATUS_CHOICES,
    })


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
            buylist = form.save()
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
        Buylist.objects.select_related('customer', 'paid_by').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    can_manage_settings = user_is_manager_or_owner(request.user)
    status_form = (
        BuylistStatusForm(instance=buylist, user=request.user)
        if can_manage_settings else None
    )
    payment_form = BuylistPaymentChoiceForm(instance=buylist) if can_manage_settings else None
    return render(request, 'buylists/buylist_detail.html', {
        'buylist': buylist,
        'status_form': status_form,
        'payment_form': payment_form,
        'can_manage_settings': can_manage_settings,
        'override_item_count': buylist.override_item_count,
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

    return response


@employee_required
def buylist_offer_sheet(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer', 'paid_by').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    return render(request, 'buylists/buylist_offer_sheet.html', {
        'buylist': buylist,
        'store_name': '[Your Store Name]',
    })


@manager_or_owner_required
@require_POST
def buylist_update_status(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    form = BuylistStatusForm(request.POST, instance=buylist, user=request.user)
    if form.is_valid():
        buylist = form.save()
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


@manager_or_owner_required
@require_POST
def buylist_update_payment_choice(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    form = BuylistPaymentChoiceForm(request.POST, instance=buylist)
    if form.is_valid():
        form.save()
        for item in buylist.items.all():
            item.save(override_user=request.user)
        if buylist.payment_choice:
            label = buylist.get_payment_choice_display()
            messages.success(request, f'Payment choice set to {label}.')
        else:
            messages.success(request, 'Payment choice cleared.')
    else:
        messages.error(request, 'Could not update payment choice.')
    return redirect('buylists:buylist_detail', pk=pk)


@employee_required
def buylistitem_create(request, buylist_pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    if request.method == 'POST':
        form = BuylistItemForm(request.POST, buylist=buylist, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.buylist = buylist
            item.save(override_user=request.user)
            messages.success(request, f'Added "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistItemForm(buylist=buylist, user=request.user)
    return render(request, 'buylists/buylistitem_form.html', {
        'form': form,
        'buylist': buylist,
        'title': 'Add Card',
    })


@employee_required
def buylistitem_edit(request, buylist_pk, pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    item = get_object_or_404(BuylistItem, pk=pk, buylist=buylist)
    if request.method == 'POST':
        form = BuylistItemForm(
            request.POST, instance=item, buylist=buylist, user=request.user,
        )
        if form.is_valid():
            form.save()
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
    item = get_object_or_404(BuylistItem, pk=pk, buylist=buylist)
    if request.method == 'POST':
        card_name = item.card_name
        item.delete()
        messages.success(request, f'Removed "{card_name}".')
        return redirect('buylists:buylist_detail', pk=buylist.pk)
    return render(request, 'buylists/buylistitem_confirm_delete.html', {
        'buylist': buylist,
        'item': item,
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
