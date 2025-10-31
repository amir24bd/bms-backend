# core/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, BloodRequest, BLOOD_GROUPS
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import date

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id','username','email','is_staff']

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    can_donate_now = serializers.SerializerMethodField()
    next_possible_donation = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['id','user','name','blood_group','city','role','ever_donated',
                  'last_donation','bio','photo','date_created','can_donate_now','next_possible_donation']

    def get_can_donate_now(self, obj):
        return obj.can_donate_now()

    def get_next_possible_donation(self, obj):
        nd = obj.next_possible_donation_date()
        return nd.isoformat() if nd else None

class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    blood_group = serializers.ChoiceField(choices=[g[0] for g in BLOOD_GROUPS])
    city = serializers.CharField()
    role = serializers.ChoiceField(choices=['donor','patient'])
    ever_donated = serializers.BooleanField(required=False)
    last_donation = serializers.DateField(required=False, allow_null=True)

    def validate(self, data):
        # if donor and ever_donated True, last_donation required
        if data['role'] == 'donor' and data.get('ever_donated', False):
            if not data.get('last_donation', None):
                raise serializers.ValidationError("Please provide last_donation date if you ever donated.")
        return data

    def create(self, validated_data):
        email = validated_data['email']
        password = validated_data['password']
        user = User.objects.create_user(username=email, email=email, password=password)
        profile = Profile.objects.create(
            user=user,
            name=validated_data['name'],
            blood_group=validated_data['blood_group'],
            city=validated_data['city'],
            role=validated_data['role'],
            ever_donated=validated_data.get('ever_donated', False),
            last_donation=validated_data.get('last_donation', None),
        )
        return user

class MyTokenObtainPairSerializer(serializers.Serializer):
    # not used; we'll use simplejwt views directly, but include tokens in user response
    pass

class BloodRequestSerializer(serializers.ModelSerializer):
    requester_profile = serializers.SerializerMethodField()
    donor_profile = serializers.SerializerMethodField()
    class Meta:
        model = BloodRequest
        fields = ['id','requester','requester_profile','donor','donor_profile','message','status','requested_at','responded_at']

    def get_requester_profile(self, obj):
        from .serializers import ProfileSerializer
        return ProfileSerializer(obj.requester.profile).data

    def get_donor_profile(self, obj):
        from .serializers import ProfileSerializer
        return ProfileSerializer(obj.donor.profile).data
