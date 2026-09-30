from django.contrib import admin
from django.urls import path
from users.views import LoginView, RefreshView, LogoutView, MeView, AddStaffView,StaffListView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("staff/add/", AddStaffView.as_view(), name="add-staff"),
    path("staff/", StaffListView.as_view(), name="staff-list"),

]