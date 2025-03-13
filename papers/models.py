# papers/models.py
from django.db import models
from django.utils import timezone
from cryptography.fernet import Fernet

FERNET_KEY = b'Z5eXdtiy1qQL1NIFVb5K7G4PXAz2NEzLjZN6g2xH6JA='

def encrypt_filename(filename: str) -> str:
    f = Fernet(FERNET_KEY)
    return f.encrypt(filename.encode()).decode()

def decrypt_filename(enc_filename: str) -> str:
    f = Fernet(FERNET_KEY)
    return f.decrypt(enc_filename.encode()).decode()


class Domain(models.Model):
    name = models.CharField(max_length=150)
    def __str__(self):
        return self.name

class Subtopic(models.Model):
    """
    Her Subtopic bir Domain'e ait.
    Örnek: Domain='Yapay Zeka ve Makine Öğrenimi', Subtopic='Derin öğrenme'
    """
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name='subtopics')
    name = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.domain.name}: {self.name}"
    
class Reviewer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    # Hakem, birden fazla alt başlığa (Subtopic) ilgi duyabilir:
    interests = models.ManyToManyField(Subtopic, related_name='reviewers', blank=True)

    def __str__(self):
        return f"{self.name} - {self.email}"


STATUS_CHOICES = (
    ("Gönderildi", "Gönderildi"),
    ("Revize Gerekli", "Revize Gerekli"),
    ("Revize", "Revize"),
    ("Anonimleştirildi", "Anonimleştirildi"),
    ("Hakeme Atandı", "Hakeme Atandı"),
    ("Değerlendirildi", "Değerlendirildi"),
    ("Final", "Final"),
)

class Submission(models.Model):
    tracking_number = models.CharField(max_length=50, unique=True)
    email_hash = models.CharField(max_length=64)
    encrypted_filename = models.TextField(null=True, blank=True)
    original_pdf = models.FileField(upload_to='uploads/')
    revised_pdf = models.FileField(upload_to='uploads/', null=True, blank=True)
    anonymized_pdf = models.FileField(upload_to='anonymized/', null=True, blank=True)
    final_pdf = models.FileField(upload_to='final/', null=True, blank=True)
    extracted_keywords = models.TextField(blank=True, null=True)
    # Makale, ilgili alt başlıkları (Subtopic) tutar.
    subtopics = models.ManyToManyField(Subtopic, blank=True, related_name='submissions')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Gönderildi')
    review = models.TextField(null=True, blank=True)
    reviewer = models.ForeignKey(Reviewer, null=True, blank=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(default=timezone.now)
    anonymized_data = models.TextField(null=True, blank=True)
    restored = models.BooleanField(default=False)
    def __str__(self):
        return f"{self.tracking_number} - {self.status}"
    def save(self, *args, **kwargs):
        if self.original_pdf and not self.encrypted_filename:
            self.encrypted_filename = encrypt_filename(self.original_pdf.name)
        super().save(*args, **kwargs)
    def get_decrypted_filename(self):
        if self.encrypted_filename:
            return decrypt_filename(self.encrypted_filename)
        return "N/A"


class Log(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    action = models.CharField(max_length=200)
    timestamp = models.DateTimeField(default=timezone.now)
    def __str__(self):
        return f"{self.submission.tracking_number} | {self.action} | {self.timestamp}"

class Message(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=50)
    sender_email = models.CharField(max_length=100, null=True, blank=True)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    def __str__(self):
        return f"{self.sender} ({self.sender_email}): {self.content[:30]}"
