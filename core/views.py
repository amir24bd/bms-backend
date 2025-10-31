# core/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status, generics
from django.contrib.auth.models import User
from .models import Profile, BloodRequest
from .serializers import ProfileSerializer, RegisterSerializer, BloodRequestSerializer, UserSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q
from .permissions import IsDonor, IsPatient, IsAdmin
from django.utils import timezone

# Custom Token serializer to add user info in response
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # add custom claims if you want
        token['email'] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        # Return JWT tokens for convenience (create using simplejwt)
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data
        return Response({
            'user': user_data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# list donors (public)
@api_view(['GET'])
def donors_list(request):
    qs = Profile.objects.filter(role='donor')
    # Filters: blood_group, city, available (can_donate_now)
    blood = request.GET.get('blood')
    city = request.GET.get('city')
    available = request.GET.get('available')
    if blood:
        qs = qs.filter(blood_group__iexact=blood)
    if city:
        qs = qs.filter(city__icontains=city)
    if available == 'true':
        qs = [p for p in qs if p.can_donate_now()]
        serializer = ProfileSerializer(qs, many=True)
        return Response(serializer.data)
    serializer = ProfileSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def profile_detail(request, pk):
    try:
        p = Profile.objects.get(id=pk)
        return Response(ProfileSerializer(p).data)
    except Profile.DoesNotExist:
        return Response({'detail':'Not found'}, status=status.HTTP_404_NOT_FOUND)

# Update profile (donor can update own)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    user = request.user
    profile = user.profile
    data = request.data
    # Only allowed fields:
    for field in ['name','blood_group','city','bio','ever_donated','last_donation']:
        if field in data:
            setattr(profile, field, data[field])
    profile.save()
    return Response(ProfileSerializer(profile).data)

# Patient sends request to a donor
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPatient])
def send_request(request, donor_id):
    donor_user = None
    try:
        donor_profile = Profile.objects.get(id=donor_id)
        if donor_profile.role != 'donor':
            return Response({'detail':'User is not a donor'}, status=status.HTTP_400_BAD_REQUEST)
        donor_user = donor_profile.user
    except Profile.DoesNotExist:
        return Response({'detail':'Donor not found'}, status=status.HTTP_404_NOT_FOUND)

    requester = request.user

    # Check blood group match
    if requester.profile.blood_group != donor_profile.blood_group:
        return Response({'detail': 'Blood group must match'}, status=status.HTTP_400_BAD_REQUEST)

    # Check donor availability (must have can_donate_now True)
    if not donor_profile.can_donate_now():
        nd = donor_profile.next_possible_donation_date()
        return Response({'detail': f"Donor not available until {nd.isoformat()}"}, status=status.HTTP_400_BAD_REQUEST)

    # Prevent duplicate pending requests from same requester to same donor
    existing = BloodRequest.objects.filter(requester=requester, donor=donor_user, status='pending')
    if existing.exists():
        return Response({'detail':'You already have a pending request to this donor'}, status=status.HTTP_400_BAD_REQUEST)

    message = request.data.get('message','')
    br = BloodRequest.objects.create(requester=requester, donor=donor_user, message=message)
    return Response(BloodRequestSerializer(br).data, status=status.HTTP_201_CREATED)

# Donor sees incoming requests
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDonor])
def donor_requests(request):
    donor_user = request.user
    qs = BloodRequest.objects.filter(donor=donor_user).order_by('-requested_at')
    return Response(BloodRequestSerializer(qs, many=True).data)

# Donor accepts/rejects a request
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsDonor])
def respond_request(request, request_id):
    action = request.data.get('action')  # 'accept' or 'reject'
    try:
        br = BloodRequest.objects.get(id=request_id, donor=request.user)
    except BloodRequest.DoesNotExist:
        return Response({'detail':'Request not found'}, status=status.HTTP_404_NOT_FOUND)
    if br.status != 'pending':
        return Response({'detail':'Request already responded'}, status=status.HTTP_400_BAD_REQUEST)

    if action == 'accept':
        br.status = 'accepted'
        br.responded_at = timezone.now()
        br.save()
        # When donor accepts and gives blood now -> update donor profile last_donation to today
        donor_profile = br.donor.profile
        donor_profile.ever_donated = True
        donor_profile.last_donation = timezone.now().date()
        donor_profile.save()
        return Response(BloodRequestSerializer(br).data)
    elif action == 'reject':
        br.status = 'rejected'
        br.responded_at = timezone.now()
        br.save()
        return Response(BloodRequestSerializer(br).data)
    else:
        return Response({'detail':'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

# Patient list their requests
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPatient])
def patient_requests(request):
    qs = BloodRequest.objects.filter(requester=request.user).order_by('-requested_at')
    return Response(BloodRequestSerializer(qs, many=True).data)

# Admin dashboard stats
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_stats(request):
    total_donors = Profile.objects.filter(role='donor').count()
    total_patients = Profile.objects.filter(role='patient').count()
    requests_pending = BloodRequest.objects.filter(status='pending').count()
    # available units by group -> count donors who can donate now by group
    groups = {}
    for g, _ in Profile._meta.get_field('blood_group').choices:
        groups[g] = Profile.objects.filter(blood_group=g)
    availability = {g: sum(1 for p in qs if p.can_donate_now()) for g, qs in groups.items()}
    return Response({
        'total_donors': total_donors,
        'total_patients': total_patients,
        'requests_pending': requests_pending,
        'availability_by_group': availability,
    })
