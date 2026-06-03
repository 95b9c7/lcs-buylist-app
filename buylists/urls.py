from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

app_name = 'buylists'

urlpatterns = [
    path('login/', LoginView.as_view(template_name='buylists/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/new/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('buylists/new/', views.buylist_create, name='buylist_create'),
    path('buylists/<int:pk>/', views.buylist_detail, name='buylist_detail'),
    path(
        'buylists/<int:pk>/offer-sheet/',
        views.buylist_offer_sheet,
        name='buylist_offer_sheet',
    ),
    path(
        'buylists/<int:pk>/export-csv/',
        views.buylist_export_csv,
        name='buylist_export_csv',
    ),
    path(
        'buylists/<int:pk>/status/',
        views.buylist_update_status,
        name='buylist_update_status',
    ),
    path(
        'buylists/<int:pk>/payment-choice/',
        views.buylist_update_payment_choice,
        name='buylist_update_payment_choice',
    ),
    path(
        'buylists/<int:pk>/unlock/',
        views.buylist_unlock_items,
        name='buylist_unlock_items',
    ),
    path(
        'buylists/<int:buylist_pk>/items/add/',
        views.buylistitem_create,
        name='buylistitem_create',
    ),
    path(
        'buylists/<int:buylist_pk>/items/<int:pk>/edit/',
        views.buylistitem_edit,
        name='buylistitem_edit',
    ),
    path(
        'buylists/<int:buylist_pk>/items/<int:pk>/delete/',
        views.buylistitem_delete,
        name='buylistitem_delete',
    ),
    path('reports/overrides/', views.override_report, name='override_report'),
    path('reports/paid/', views.paid_report, name='paid_report'),
    path('pricing-rules/', views.pricing_rule_list, name='pricing_rule_list'),
    path('pricing-rules/new/', views.pricing_rule_create, name='pricing_rule_create'),
    path(
        'pricing-rules/<int:pk>/edit/',
        views.pricing_rule_edit,
        name='pricing_rule_edit',
    ),
]
