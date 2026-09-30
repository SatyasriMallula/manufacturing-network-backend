from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from rest_framework import serializers
from .models import User

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "organization": None,
            "roles": list(user.groups.values_list("name", flat=True)),
            "is_superuser": user.is_superuser,
        }

        if user.organization:
            data["user"]["organization"] = {
                "id": str(user.organization.id),
                "name": user.organization.name,
            }

        return data

class AddStaffSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[
        "company_admin", "engineering", "purchase", "sales",
        "production", "quality", "finance", "vendor", "customer",
    ])

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        requesting_user = self.context["request"].user

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            organization=requesting_user.organization,  # always their own org
        )

        role_group, _ = Group.objects.get_or_create(name=validated_data["role"])
        user.groups.add(role_group)

        return user
    
class StafflistSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active", "roles", "date_joined"]

    def get_roles(self, obj):
        return list(obj.groups.values_list("name", flat=True))