from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from rest_framework import serializers
from .models import User
from organizations.models import Organization

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
    organization = serializers.UUIDField(required=False)  # Super Admin only
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[
        "company_admin", "engineering", "purchase", "sales",
        "production", "quality", "finance", "vendor", "customer",
    ])

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        requesting_user = self.context["request"].user

        if requesting_user.is_superuser:
            org_id = attrs.get("organization")
            if not org_id:
                raise serializers.ValidationError({"organization": "Required when adding staff as Super Admin."})
            try:
                attrs["organization_obj"] = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                raise serializers.ValidationError({"organization": "Organization not found."})
        else:
            if not requesting_user.organization:
                raise serializers.ValidationError("Your account is not linked to an organization.")
            attrs["organization_obj"] = requesting_user.organization  # input ignored

        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            organization=validated_data["organization_obj"],
        )
        role_group, _ = Group.objects.get_or_create(name=validated_data["role"])
        user.groups.add(role_group)
        return user
    
class StafflistSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "is_active",
            "organization", "organization_name", "roles", "date_joined",
        ]

    def get_roles(self, obj):
        return [g.name for g in obj.groups.all()]