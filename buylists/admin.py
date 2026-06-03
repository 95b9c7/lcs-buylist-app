from django.contrib import admin

from .models import Buylist, BuylistItem, Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']
    search_fields = ['name', 'email', 'phone']


class BuylistItemInline(admin.TabularInline):
    model = BuylistItem
    extra = 0
    readonly_fields = ['cash_offer_price', 'trade_offer_price']


@admin.register(Buylist)
class BuylistAdmin(admin.ModelAdmin):
    list_display = ['customer', 'status', 'created_at', 'updated_at']
    list_filter = ['status']
    search_fields = ['customer__name']
    inlines = [BuylistItemInline]


@admin.register(BuylistItem)
class BuylistItemAdmin(admin.ModelAdmin):
    list_display = [
        'card_name',
        'set_name',
        'buylist',
        'quantity',
        'condition',
        'market_price',
        'cash_offer_price',
        'trade_offer_price',
    ]
    list_filter = ['condition']
    readonly_fields = ['cash_offer_price', 'trade_offer_price']
