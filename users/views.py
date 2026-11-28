from django.shortcuts import render
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from core.permissions import  IsCompanyAdminOrSuperuser
from .serializers import MyTokenObtainPairSerializer,AddStaffSerializer, StafflistSerializer
from core.responses import success_response,error_response
from .models import User  
import uuid
from core.pagination import StandardPagination
from rest_framework.permissions import AllowAny
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.throttling import ScopedRateThrottle


def set_auth_cookies(response,access,refresh):
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS,
        access,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
 max_age=settings.ACCESS_TOKEN_MAX_AGE,
 )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH,
        refresh,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_MAX_AGE,

    )

class LoginView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        response = success_response(
            message="Login Successfull",
            data=data["user"],
            status_code=200
        )
        
        set_auth_cookies(response, str(data["access"]), str(data["refresh"]))
        print("LOGIN RESPONSE COOKIES:", response.cookies)
        return response
    
    
class RefreshView(APIView):
    authentication_classes = []      
    permission_classes = [AllowAny] 
    def post(self, request):
        refresh_token = request.COOKIES.get(
            settings.AUTH_COOKIE_REFRESH
        )

        if not refresh_token:
            return error_response(
                message="No refresh token",
                status_code=401
            )

        try:
            refresh = RefreshToken(refresh_token)
            new_access = str(refresh.access_token)

        except TokenError:
            return error_response(
                message="Invalid or expired refresh token",
                status_code=401
            )

        response = success_response(
            message="New access token generated successfully",
            status_code=200
        )

        response.set_cookie(
            settings.AUTH_COOKIE_ACCESS,
            new_access,
            httponly=True,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )

        return response


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]    
    def post(self, request):
        refresh_token = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        response = success_response(message="Loged out successfully")
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS)
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH)
        return response

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        data = {
            "id": str(user.id),
            "email": user.email,
            "roles": list(user.groups.values_list("name", flat=True)),
            "permissions": sorted(user.get_all_permissions()),
            "is_superuser": user.is_superuser,
        }

        if user.organization:
            data["organization"] = {
                "id": str(user.organization.id),
                "name": user.organization.name,
            }

        return success_response(
            message="User data fetched successfully",
            data=data,
            status_code=200,
        )
        
        
    
class AddStaffView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperuser]
    required_permission = "users.add_user"

    def post(self, request):
        serializer = AddStaffSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return success_response(
            message="Staff member added successfully",
            data={
                "id": str(user.id),
                "email": user.email,
                "organization": user.organization.name,
                "roles": list(user.groups.values_list("name", flat=True)),
            },
            status_code=201,
        )


class StaffListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperuser]

    def get(self, request):
        staff = User.objects.select_related("organization").prefetch_related("groups")

        if request.user.is_superuser:
            organization_id = request.query_params.get("organization_id")
            if organization_id:
                try:
                    uuid.UUID(organization_id)
                except ValueError:
                    return success_response(message="Invalid organization_id", data=None, status_code=400)
                staff = staff.filter(organization_id=organization_id)
        else:
            if not request.user.organization:
                return success_response(message="No organization linked to this user", data=[])
            staff = staff.filter(organization=request.user.organization)

        staff = staff.order_by("-date_joined")

        paginator = StandardPagination()
        page = paginator.paginate_queryset(staff, request)
        serializer = StafflistSerializer(page, many=True)

        return success_response(
            message="Staff fetched successfully",
            **paginator.get_pagination_meta(),
            data=serializer.data,

        )



class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old = request.data.get("old_password") or ""
        new = request.data.get("new_password") or ""
        user = request.user

        if not user.check_password(old):
            return error_response("Current password is incorrect", status_code=400)
        try:
            validate_password(new, user=user)
        except DjangoValidationError as exc:
            return error_response("Choose a stronger password", errors={"new_password": list(exc.messages)}, status_code=400)

        user.set_password(new)
        user.save(update_fields=["password"])
        return success_response(message="Password changed", data=None)