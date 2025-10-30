from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, BloodRequest, BLOOD_GROUPS
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import date
from django.utils import timezone

class UserSerializer(serializers.ModelSerializer):
    # Provide a convenient name property (full name from profile if present)
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_staff', 'name']

    def get_name(self, obj):
        # Prefer profile.name if available, then first_name/last_name, then username
        try:
            if hasattr(obj, 'profile') and obj.profile and obj.profile.name:
                return obj.profile.name
        except Exception:
            pass
        full = (obj.first_name or "") + (" " if obj.first_name and obj.last_name else "") + (obj.last_name or "")
        full = full.strip()
        if full:
            return full
        return obj.username or obj.email or ""

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    can_donate_now = serializers.SerializerMethodField()
    next_possible_donation = serializers.SerializerMethodField()
    # Provide convenient URL field for frontend
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['id','user','name','blood_group','city','role','ever_donated',
                  'last_donation','bio','photo','photo_url','date_created',
                  'can_donate_now','next_possible_donation']

    def get_can_donate_now(self, obj):
        return obj.can_donate_now()

    def get_next_possible_donation(self, obj):
        nd = obj.next_possible_donation_date()
        return nd.isoformat() if nd else None

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request') if isinstance(self.context, dict) else None
        try:
            if request:
                return request.build_absolute_uri(obj.photo.url)
        except Exception:
            pass
        return obj.photo.url


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    blood_group = serializers.ChoiceField(choices=[g[0] for g in BLOOD_GROUPS])
    city = serializers.CharField()
    role = serializers.ChoiceField(choices=['donor','patient'])
    ever_donated = serializers.BooleanField(required=False)
    last_donation = serializers.DateField(required=False, allow_null=True)
    # accept image upload
    photo = serializers.ImageField(required=False, allow_null=True)

    def validate(self, data):
        if data['role'] == 'donor' and data.get('ever_donated', False):
            if not data.get('last_donation', None):
                raise serializers.ValidationError("Please provide last_donation date if you ever donated.")
        return data

    def create(self, validated_data):
        email = validated_data['email']
        password = validated_data['password']
        # create user
        user = User.objects.create_user(username=email, email=email, password=password)
        # create or update the profile
        profile_vals = {
            'name': validated_data.get('name', email),
            'blood_group': validated_data.get('blood_group'),
            'city': validated_data.get('city'),
            'role': validated_data.get('role', 'patient'),
            'ever_donated': validated_data.get('ever_donated', False),
            'last_donation': validated_data.get('last_donation', None),
            'bio': validated_data.get('bio', ''),
        }
        photo = validated_data.get('photo', None)
        if photo:
            profile_vals['photo'] = photo

        Profile.objects.update_or_create(user=user, defaults=profile_vals)
        return user


class MyTokenObtainPairSerializer(serializers.Serializer):
    # placeholder: actual token serializer is in views (we don't use this class directly here)
    pass


class BloodRequestSerializer(serializers.ModelSerializer):
    requester_profile = serializers.SerializerMethodField()
    donor_profile = serializers.SerializerMethodField()
    class Meta:
        model = BloodRequest
        fields = ['id','requester','requester_profile','donor','donor_profile','message','status','requested_at','responded_at']

    def get_requester_profile(self, obj):
        from .serializers import ProfileSerializer
        ctx = self.context if hasattr(self, 'context') else {}
        try:
            return ProfileSerializer(obj.requester.profile, context=ctx).data
        except Exception:
            return None

    def get_donor_profile(self, obj):
        from .serializers import ProfileSerializer
        ctx = self.context if hasattr(self, 'context') else {}
        try:
            return ProfileSerializer(obj.donor.profile, context=ctx).data
        except Exception:
            return None
