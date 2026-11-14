from rest_framework.permissions import BasePermission

BUYER_ROLES = ("company_admin", "purchase")
VENDOR_ROLES = ("company_admin", "sales")
FINANCE_ROLES = ("company_admin", "finance")

def has_role(user, *roles):
    return user.is_superuser or user.groups.filter(name__in=roles).exists()

class IsCompanyAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name="company_admin").exists()


class HasPermission(BasePermission):

    def has_permission(self, request, view):
        permission = view.required_permission
        print("permission",permission)
        return request.user.has_perm(permission)
    

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_superuser

from rest_framework.permissions import BasePermission

class IsCompanyAdminOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (
                request.user.is_superuser
                or request.user.groups.filter(name="company_admin").exists()
            )
        )