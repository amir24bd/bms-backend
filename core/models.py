# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

BLOOD_GROUPS = [
    ('A+', 'A+'),('A-','A-'),('B+','B+'),('B-','B-'),
    ('O+','O+'),('O-','O-'),('AB+','AB+'),('AB-','AB-'),
]

ROLE_CHOICES = [
    ('donor','Donor'),
    ('patient','Patient'),
    ('admin','Admin'),  # admin role is optional; admin users should be staff
]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    name = models.CharField(max_length=200)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS)
    city = models.CharField(max_length=100)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='patient')
    # donor-specific
    ever_donated = models.BooleanField(default=False)
    last_donation = models.DateField(null=True, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='profiles/', null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    def can_donate_now(self):
        """
        A donor can donate if either never donated OR last_donation >= 90 days ago.
        """
        if not self.ever_donated or not self.last_donation:
            return True
        next_possible = self.last_donation + timedelta(days=90)
        return timezone.now().date() >= next_possible

    def next_possible_donation_date(self):
        if not self.last_donation:
            return None
        return self.last_donation + timedelta(days=90)

    def __str__(self):
        return f"{self.name} ({self.blood_group})"
    

class BloodRequest(models.Model):
    STATUS_CHOICES = [
        ('pending','Pending'),
        ('accepted','Accepted'),
        ('rejected','Rejected'),
    ]
    requester = models.ForeignKey(User, related_name='requests_made', on_delete=models.CASCADE)  # patient
    donor = models.ForeignKey(User, related_name='requests_received', on_delete=models.CASCADE)   # donor user
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Request {self.id} from {self.requester.email} -> {self.donor.email}"
