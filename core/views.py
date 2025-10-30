from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from .models import Profile, BloodRequest
from .serializers import (
    ProfileSerializer,
    RegisterSerializer,
    BloodRequestSerializer,
    UserSerializer,
)
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import IntegrityError
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone


# ---------------------------
# JWT Token View
# ---------------------------
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user_data = UserSerializer(self.user).data
        try:
            profile_data = ProfileSerializer(
                self.user.profile, context={"request": self.context.get("request")}
            ).data
        except Exception:
            profile_data = None
        user_data["profile"] = profile_data
        data["user"] = user_data
        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# ---------------------------
# Register new user
# ---------------------------
@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
        except IntegrityError:
            return Response(
                {"detail": "User with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data
        try:
            profile_data = ProfileSerializer(
                user.profile, context={"request": request}
            ).data
        except Exception:
            profile_data = None
        user_data["profile"] = profile_data

        return Response(
            {
                "user": user_data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------
# Donor list & profiles
# ---------------------------
@api_view(["GET"])
def donors_list(request):
    qs = Profile.objects.filter(role="donor")
    blood = request.GET.get("blood")
    city = request.GET.get("city")
    available = request.GET.get("available")

    if blood:
        qs = qs.filter(blood_group__iexact=blood)
    if city:
        qs = qs.filter(city__icontains=city)
    if available == "true":
        qs = [p for p in qs if p.can_donate_now()]
        serializer = ProfileSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    serializer = ProfileSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
def profile_detail(request, pk):
    try:
        profile = Profile.objects.get(id=pk)
        return Response(ProfileSerializer(profile, context={"request": request}).data)
    except Profile.DoesNotExist:
        return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_profile(request):
    user = request.user
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return Response(
            {"detail": "Profile not found for user"}, status=status.HTTP_404_NOT_FOUND
        )

    data = request.data
    for field in [
        "name",
        "blood_group",
        "city",
        "bio",
        "ever_donated",
        "last_donation",
    ]:
        if field in data:
            val = data[field]
            if field == "ever_donated" and isinstance(val, str):
                val = val.lower() in ("1", "true", "yes")
            setattr(profile, field, val)

    if "photo" in request.FILES:
        profile.photo = request.FILES["photo"]

    profile.save()
    return Response(ProfileSerializer(profile, context={"request": request}).data)


# ---------------------------
# Blood Requests (Patient ↔ Donor)
# ---------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_request(request, donor_id):
    """
    Patient sends blood request to a donor.
    """
    message = request.data.get("message", "")
    donor_profile = get_object_or_404(Profile, id=donor_id, role="donor")
    donor_user = donor_profile.user

    if request.user == donor_user:
        return Response(
            {"detail": "You cannot send request to yourself."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    blood_request = BloodRequest.objects.create(
        requester=request.user, donor=donor_user, message=message
    )
    return Response(
        BloodRequestSerializer(blood_request, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donor_requests(request):
    """
    Donor views all incoming requests
    """
    user = request.user
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        return Response({"detail": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

    if profile.role != "donor":
        return Response(
            {"detail": "Only donors can access this endpoint."},
            status=status.HTTP_403_FORBIDDEN,
        )

    qs = BloodRequest.objects.filter(donor=user).order_by("-requested_at")
    serializer = BloodRequestSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_request(request, request_id):
    """
    Donor accepts or rejects a request.
    If accepted -> donor profile updates: ever_donated=True, last_donation=today
    """
    status_value = request.data.get("status")
    if status_value not in ("accepted", "rejected"):
        return Response(
            {"detail": 'Invalid status. Use "accepted" or "rejected".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    br = get_object_or_404(BloodRequest, id=request_id)

    if br.donor != request.user:
        return Response(
            {"detail": "Only the donor can respond to this request."},
            status=status.HTTP_403_FORBIDDEN,
        )

    br.status = status_value
    br.responded_at = timezone.now()
    br.save()

    # ✅ Auto update donor's profile if accepted
    if status_value == "accepted":
        try:
            donor_profile = request.user.profile
            donor_profile.ever_donated = True
            donor_profile.last_donation = timezone.now().date()
            donor_profile.save()
        except Profile.DoesNotExist:
            pass

    return Response(BloodRequestSerializer(br, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def patient_requests(request):
    """
    Patient views all requests they have sent.
    """
    qs = BloodRequest.objects.filter(requester=request.user).order_by("-requested_at")
    serializer = BloodRequestSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data)


# ---------------------------
# Admin statistics
# ---------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_stats(request):
    if not request.user.is_staff:
        return Response(
            {"detail": "Admin only."}, status=status.HTTP_403_FORBIDDEN
        )

    donors_count = Profile.objects.filter(role="donor").count()
    patients_count = Profile.objects.filter(role="patient").count()
    pending_requests = BloodRequest.objects.filter(status="pending").count()

    data = {
        "donors": donors_count,
        "patients": patients_count,
        "pending_requests": pending_requests,
    }
    return Response(data)
