import re
from django import forms
from django.core.exceptions import ValidationError

def strict_email_validator(value):
    pattern = r'^[\w\.-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,3}$'
    if not re.match(pattern, value):
        raise ValidationError("Lütfen geçerli bir e-posta adresi giriniz. Örnek: ornek@gmail.com")

class UploadForm(forms.Form):
    email = forms.EmailField(label='E-posta Adresi', validators=[strict_email_validator])
    pdf_file = forms.FileField(label='PDF Dosyası')

    def clean_pdf_file(self):
        pdf = self.cleaned_data.get('pdf_file')
        if pdf and not pdf.name.lower().endswith('.pdf'):
            raise forms.ValidationError("Sadece PDF yükleyebilirsiniz.")
        return pdf

class ReviseForm(forms.Form):
    pdf_file = forms.FileField(label='Revize Edilmiş PDF Dosyası')

    def clean_pdf_file(self):
        pdf = self.cleaned_data.get('pdf_file')
        if pdf and not pdf.name.lower().endswith('.pdf'):
            raise forms.ValidationError("Sadece PDF yükleyebilirsiniz.")
        return pdf

class StatusForm(forms.Form):
    tracking_number = forms.CharField(label='Takip Numarası')
    email = forms.EmailField(label='E-posta Adresi', validators=[strict_email_validator])

class ReviewForm(forms.Form):
    review_text = forms.CharField(label='Değerlendirme Notları', widget=forms.Textarea)

class MessageForm(forms.Form):
    email = forms.EmailField(label='E-posta Adresi (gönderen)', validators=[strict_email_validator])
    content = forms.CharField(label='Mesajınız', widget=forms.Textarea)

class ReplyForm(forms.Form):
    content = forms.CharField(
        label='Cevabınız',
        widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Mesajınızı buraya yazın...'})
    )

class AnonymizeOptionsForm(forms.Form):
    anonymize_name = forms.BooleanField(label="Yazar Ad-Soyad", required=False)
    anonymize_contact = forms.BooleanField(label="Yazar İletişim Bilgileri", required=False)
    anonymize_institution = forms.BooleanField(label="Yazar Kurum Bilgileri", required=False)
