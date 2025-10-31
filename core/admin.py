# core/admin.py
from django.contrib import admin
from .models import Profile, BloodRequest

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('name','user','blood_group','city','role','ever_donated','last_donation')

@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ('id','requester','donor','status','requested_at','responded_at')
