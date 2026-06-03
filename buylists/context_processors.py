from .permissions import user_is_manager_or_owner, user_is_owner


def nav_permissions(request):
    user = request.user
    return {
        'nav_is_authenticated': user.is_authenticated,
        'nav_username': user.get_username() if user.is_authenticated else '',
        'nav_is_owner': user_is_owner(user),
        'nav_is_manager_or_owner': user_is_manager_or_owner(user),
        'nav_can_view_override_report': user_is_manager_or_owner(user),
        'nav_can_view_paid_report': user_is_manager_or_owner(user),
    }
