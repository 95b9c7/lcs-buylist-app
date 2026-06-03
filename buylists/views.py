from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    BuylistForm,
    BuylistItemForm,
    BuylistPaymentChoiceForm,
    BuylistStatusForm,
    CustomerForm,
)
from .models import Buylist, BuylistItem, Customer


def dashboard(request):
    buylists = Buylist.objects.select_related('customer')[:20]
    return render(request, 'buylists/dashboard.html', {'buylists': buylists})


def customer_list(request):
    customers = Customer.objects.all()
    return render(request, 'buylists/customer_list.html', {'customers': customers})


def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Customer "{customer.name}" created.')
            return redirect('buylists:customer_list')
    else:
        form = CustomerForm()
    return render(request, 'buylists/customer_form.html', {
        'form': form,
        'title': 'New Customer',
    })


def buylist_create(request):
    if request.method == 'POST':
        form = BuylistForm(request.POST)
        if form.is_valid():
            buylist = form.save()
            messages.success(request, 'Buylist created.')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistForm()
    return render(request, 'buylists/buylist_form.html', {
        'form': form,
        'title': 'New Buylist',
    })


def buylist_detail(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer').prefetch_related('items'),
        pk=pk,
    )
    status_form = BuylistStatusForm(instance=buylist)
    payment_form = BuylistPaymentChoiceForm(instance=buylist)
    return render(request, 'buylists/buylist_detail.html', {
        'buylist': buylist,
        'status_form': status_form,
        'payment_form': payment_form,
    })


def buylist_offer_sheet(request, pk):
    buylist = get_object_or_404(
        Buylist.objects.select_related('customer').prefetch_related('items'),
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
        form = BuylistItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.buylist = buylist
            item.save()
            messages.success(request, f'Added "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistItemForm()
    return render(request, 'buylists/buylistitem_form.html', {
        'form': form,
        'buylist': buylist,
        'title': 'Add Card',
    })


def buylistitem_edit(request, buylist_pk, pk):
    buylist = get_object_or_404(Buylist, pk=buylist_pk)
    item = get_object_or_404(BuylistItem, pk=pk, buylist=buylist)
    if request.method == 'POST':
        form = BuylistItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f'Updated "{item.card_name}".')
            return redirect('buylists:buylist_detail', pk=buylist.pk)
    else:
        form = BuylistItemForm(instance=item)
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
