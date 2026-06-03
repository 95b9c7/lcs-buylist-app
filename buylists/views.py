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
)
from .models import Buylist, BuylistItem, Customer, round_money


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

    # Sum() in SQLite can return extra decimal places (e.g. 12.6000000000000).
    for customer in customers:
        customer.total_offered = round_money(customer.total_offered)

    return render(request, 'buylists/customer_list.html', {
        'customers': customers,
        'search_query': search_query,
    })


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


def buylist_create(request):
    customer = None
    customer_pk = request.GET.get('customer')
    if customer_pk:
        customer = get_object_or_404(Customer, pk=customer_pk)

    if request.method == 'POST':
        form = BuylistForm(request.POST)
        if form.is_valid():
            buylist = form.save()
            messages.success(request, 'Buylist created.')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        initial = {'customer': customer} if customer else None
        form = BuylistForm(initial=initial)

    return render(request, 'buylists/buylist_form.html', {
        'form': form,
        'title': 'New Buylist',
        'customer': customer,
    })


def buylist_detail(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    status_form = BuylistStatusForm(instance=buylist)
    payment_form = BuylistPaymentChoiceForm(instance=buylist)
    return render(request, 'buylists/buylist_detail.html', {
        'buylist': buylist,
        'status_form': status_form,
        'payment_form': payment_form,
    })


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
            item.notes,
        ])

    return response


def buylist_offer_sheet(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer').prefetch_related(
            'items__override_by',
        ),
        pk=pk,
    )
    return render(request, 'buylists/buylist_offer_sheet.html', {
        'buylist': buylist,
        'store_name': '[Your Store Name]',
    })


@require_POST
def buylist_update_status(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    form = BuylistStatusForm(request.POST, instance=buylist)
    if form.is_valid():
        form.save()
        messages.success(request, f'Status updated to {buylist.get_status_display()}.')
    else:
        messages.error(request, 'Could not update status.')
    return redirect('buylists:buylist_detail', pk=pk)


@require_POST
def buylist_update_payment_choice(request, pk):
    buylist = get_object_or_404(Buylist, pk=pk)
    form = BuylistPaymentChoiceForm(request.POST, instance=buylist)
    if form.is_valid():
        form.save()
        for item in buylist.items.all():
            item.save()
        if buylist.payment_choice:
            label = buylist.get_payment_choice_display()
            messages.success(request, f'Payment choice set to {label}.')
        else:
            messages.success(request, 'Payment choice cleared.')
    else:
        messages.error(request, 'Could not update payment choice.')
    return redirect('buylists:buylist_detail', pk=pk)


def buylistitem_create(request, buylist_pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    if request.method == 'POST':
        form = BuylistItemForm(request.POST, buylist=buylist, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.buylist = buylist
            item.save()
            messages.success(request, f'Added "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistItemForm(buylist=buylist, user=request.user)
    return render(request, 'buylists/buylistitem_form.html', {
        'form': form,
        'buylist': buylist,
        'title': 'Add Card',
    })


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
