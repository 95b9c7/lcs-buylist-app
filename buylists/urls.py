from django.urls import path

from . import views

app_name = 'buylists'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/new/', views.customer_create, name='customer_create'),
    path('buylists/new/', views.buylist_create, name='buylist_create'),
    path('buylists/<int:pk>/', views.buylist_detail, name='buylist_detail'),
    path(
        'buylists/<int:pk>/status/',
        views.buylist_update_status,
        name='buylist_update_status',
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
]
