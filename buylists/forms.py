from django import forms

from .models import Buylist, BuylistItem, Customer


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


class BuylistStatusForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Buylist
        fields = ['status']
        labels = {'status': 'Update status'}


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
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['condition_percent'].help_text = (
            'Auto-filled from condition; you can override. '
            'Cash offer uses 60%, trade credit uses 70%.'
        )

        if not self.instance.pk and not self.is_bound:
            condition = self.initial.get('condition', BuylistItem.CONDITION_NM)
            self.fields['condition_percent'].initial = (
                BuylistItem.condition_percent_for(condition)
            )

    def clean(self):
        cleaned = super().clean()
        condition = cleaned.get('condition')
        if not condition:
            return cleaned

        if not self.instance.pk or 'condition' in self.changed_data:
            cleaned['condition_percent'] = BuylistItem.condition_percent_for(condition)

        return cleaned
