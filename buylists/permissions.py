from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

GROUP_EMPLOYEE = 'Employee'
GROUP_MANAGER = 'Manager'
GROUP_OWNER = 'Owner'


def user_group_names(user):
    if not user.is_authenticated:
        return set()
    return set(user.groups.values_list('name', flat=True))


def user_is_owner(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or GROUP_OWNER in user_group_names(user)


def user_is_manager_or_owner(user):
    if not user.is_authenticated:
        return False
    if user_is_owner(user):
        return True
    return GROUP_MANAGER in user_group_names(user)


def user_is_employee(user):
    """Any logged-in staff member (Employee group or higher)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    groups = user_group_names(user)
    return bool(
        groups & {GROUP_EMPLOYEE, GROUP_MANAGER, GROUP_OWNER}
        or not groups
    )


def owner_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not user_is_owner(request.user):
            raise PermissionDenied('Owner access is required for this page.')
        return view_func(request, *args, **kwargs)
    return wrapper


def manager_or_owner_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not user_is_manager_or_owner(request.user):
            raise PermissionDenied(
                'Manager or Owner access is required for buylist settings.'
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def employee_required(view_func):
    """Require login for buylist and customer work."""
    return login_required(view_func)
