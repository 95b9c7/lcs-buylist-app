from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Buylist, BuylistItem, Customer, PricingRule, round_money
from .offer_rules import get_role_label, validate_final_offer
from .permissions import user_is_manager_or_owner


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = 'form-control'
            if isinstance(field.widget, forms.Select):
                css = 'form-select'
            field.widget.attrs.setdefault('class', css)


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class BuylistForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Buylist
        fields = ['customer', 'status']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user_is_manager_or_owner(user):
            if 'status' in self.fields:
                del self.fields['status']


class PricingRuleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PricingRule
        fields = [
            'name',
            'min_market_price',
            'max_market_price',
            'offer_percent',
            'is_active',
        ]
        widgets = {
            'offer_percent': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['offer_percent'].help_text = 'Decimal rate (0.70 = 70%).'


class BuylistStatusForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Buylist
        fields = ['status']
        labels = {'status': 'Update status'}


class BuylistPaymentChoiceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Buylist
        fields = ['payment_choice']
        labels = {'payment_choice': 'Customer payment choice'}


class BuylistItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BuylistItem
        fields = [
            'card_name',
            'set_name',
            'quantity',
            'condition',
            'market_price',
            'condition_percent',
            'final_offer_price',
            'override_reason',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
            'override_reason': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.buylist = kwargs.pop('buylist', None)
        super().__init__(*args, **kwargs)

        self.fields['condition_percent'].help_text = (
            'Auto-filled from condition; you can override.'
        )
        self.fields['override_reason'].help_text = (
            'Required if final offer is above the recommended offer.'
        )
        self.fields['final_offer_price'].help_text = get_role_label(self.user)

        if not self.instance.pk:
            self.fields.pop('final_offer_price')
            self.fields.pop('override_reason')
            condition = self.initial.get('condition', BuylistItem.CONDITION_NM)
            self.fields['condition_percent'].initial = (
                BuylistItem.condition_percent_for(condition)
            )
        elif self.buylist and not self.buylist.payment_choice_selected:
            self.fields['final_offer_price'].help_text += (
                ' Payment choice not set; recommended uses 70% trade rate.'
            )

    def _build_item_for_recommended(self, cleaned_data):
        item = self.instance if self.instance.pk else BuylistItem()
        for field in [
            'card_name', 'set_name', 'quantity', 'condition',
            'market_price', 'condition_percent',
        ]:
            if field in cleaned_data:
                setattr(item, field, cleaned_data[field])
        if self.buylist:
            item.buylist = self.buylist
        return item

    def clean(self):
        cleaned = super().clean()
        condition = cleaned.get('condition')
        if condition and (not self.instance.pk or 'condition' in self.changed_data):
            cleaned['condition_percent'] = BuylistItem.condition_percent_for(condition)

        if not self.instance.pk:
            return cleaned

        item = self._build_item_for_recommended(cleaned)
        recommended = item.calculate_recommended_offer_price()
        final = round_money(cleaned.get('final_offer_price'))
        cleaned['final_offer_price'] = final
        override_reason = cleaned.get('override_reason', '')

        for error in validate_final_offer(
            self.user, recommended, final, override_reason
        ):
            if 'Override reason' in error:
                self.add_error('override_reason', error)
            else:
                self.add_error('final_offer_price', error)

        cleaned['recommended_offer_price'] = recommended
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.instance.pk and 'recommended_offer_price' in self.cleaned_data:
            instance.recommended_offer_price = self.cleaned_data['recommended_offer_price']

            if instance.final_offer_price > instance.recommended_offer_price:
                if self.user and self.user.is_authenticated:
                    instance.override_by = self.user
                instance.override_at = timezone.now()
            else:
                instance.override_reason = ''
                instance.override_by = None
                instance.override_at = None

        if commit:
            instance.save()
        return instance
