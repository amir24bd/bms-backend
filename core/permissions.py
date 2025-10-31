# core/permissions.py
from rest_framework.permissions import BasePermission

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

class IsDonor(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and hasattr(request.user,'profile') and request.user.profile.role == 'donor')

class IsPatient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and hasattr(request.user,'profile') and request.user.profile.role == 'patient')
