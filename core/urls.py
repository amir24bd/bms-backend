# core/urls.py
from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Auth
    path('users/register/', views.register_view, name='register'),
    path('users/login/', views.MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('users/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Profiles & donors
    path('donors/', views.donors_list, name='donors-list'),
    path('profile/<int:pk>/', views.profile_detail, name='profile-detail'),
    path('profile/update/', views.update_profile, name='profile-update'),

    # Requests
    path('requests/send/<int:donor_id>/', views.send_request, name='send-request'),
    path('requests/donor/', views.donor_requests, name='donor-requests'),
    path('requests/respond/<int:request_id>/', views.respond_request, name='respond-request'),
    path('requests/patient/', views.patient_requests, name='patient-requests'),

    # Admin
    path('admin/stats/', views.admin_stats, name='admin-stats'),
]
