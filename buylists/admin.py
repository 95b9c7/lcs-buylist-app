from django.contrib import admin

from .models import Buylist, BuylistActivity, BuylistItem, Customer, PricingRule
from .permissions import user_is_owner


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email']
    search_fields = ['name', 'phone', 'email']
    list_per_page = 25
    ordering = ['name']


class BuylistItemInline(admin.TabularInline):
    model = BuylistItem
    extra = 1
    fields = [
        'card_name',
        'set_name',
        'quantity',
        'condition',
        'market_price',
        'condition_percent',
        'recommended_offer_price',
        'final_offer_price',
        'override_reason',
        'notes',
    ]
    readonly_fields = [
        'cash_offer_price',
        'trade_offer_price',
        'recommended_offer_price',
    ]


@admin.register(Buylist)
class BuylistAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'status', 'payment_method',
        'amount_paid', 'paid_at', 'created_at',
    ]
    list_filter = ['status', 'payment_method', ('created_at', admin.DateFieldListFilter)]
    search_fields = ['customer__name']
    autocomplete_fields = ['customer']
    readonly_fields = [
        'created_at', 'updated_at', 'paid_at', 'paid_by',
        'unlocked_at', 'unlocked_by',
    ]
    inlines = [BuylistItemInline]
    list_per_page = 25
    date_hierarchy = 'created_at'
    fieldsets = (
        (None, {
            'fields': ('customer', 'status', 'payment_choice'),
        }),
        ('Store payment (when Paid)', {
            'fields': ('payment_method', 'amount_paid', 'paid_at', 'paid_by'),
        }),
        ('Item unlock (Accepted)', {
            'fields': ('unlock_reason', 'unlocked_by', 'unlocked_at'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(BuylistItem)
class BuylistItemAdmin(admin.ModelAdmin):
    list_display = [
        'card_name',
        'set_name',
        'quantity',
        'condition',
        'market_price',
        'recommended_offer_price',
        'final_offer_price',
    ]
    list_filter = ['condition']
    search_fields = ['card_name', 'set_name']
    autocomplete_fields = ['buylist']
    readonly_fields = [
        'cash_offer_price',
        'trade_offer_price',
        'recommended_offer_price',
        'override_recommended_price',
        'override_final_price',
        'override_by',
        'override_at',
    ]
    list_per_page = 25
    fieldsets = (
        ('Card', {
            'fields': ('buylist', 'card_name', 'set_name', 'quantity', 'condition', 'notes'),
        }),
        ('Pricing', {
            'fields': (
                'market_price',
                'condition_percent',
                'cash_offer_price',
                'trade_offer_price',
                'recommended_offer_price',
                'final_offer_price',
            ),
        }),
        ('Override', {
            'fields': (
                'override_recommended_price',
                'override_final_price',
                'override_reason',
                'override_by',
                'override_at',
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(BuylistActivity)
class BuylistActivityAdmin(admin.ModelAdmin):
    list_display = ['id', 'buylist', 'user', 'action', 'created_at']
    list_filter = ['action', ('created_at', admin.DateFieldListFilter)]
    search_fields = ['buylist__id', 'user__username', 'description']
    readonly_fields = ['buylist', 'user', 'action', 'description', 'created_at']
    list_per_page = 50
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'min_market_price',
        'max_market_price',
        'offer_percent',
        'is_active',
    ]
    list_filter = ['is_active']
    list_per_page = 25
    search_fields = ['name']
    ordering = ['min_market_price', 'name']

    def has_module_permission(self, request):
        return user_is_owner(request.user)

    def has_view_permission(self, request, obj=None):
        return user_is_owner(request.user)

    def has_add_permission(self, request):
        return user_is_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return user_is_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return user_is_owner(request.user)
