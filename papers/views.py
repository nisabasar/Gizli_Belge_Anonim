import os, hashlib, uuid
from django.shortcuts import get_object_or_404, render, redirect
from django.conf import settings
from django.contrib import messages
from .models import Submission, Log, Message, Domain, Reviewer
from .forms import UploadForm, ReviseForm, StatusForm, ReviewForm, MessageForm
from .nlp_utils import extract_keywords_from_pdf_advanced as extract_keywords_from_pdf_nlp
from .anonymization import anonymize_pdf, merge_review_comments

def generate_tracking_number():
    return str(uuid.uuid4())[:8]

def hash_email(email):
    return hashlib.sha256(email.encode('utf-8')).hexdigest()

# KULLANICI (Yazar) Süreci
def home(request):
    return render(request, 'home.html')

def upload_paper(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data['email']
            pdf_file = form.cleaned_data['pdf_file']
            tracking = generate_tracking_number()
            hashed = hash_email(email)
            submission = Submission.objects.create(
                tracking_number=tracking,
                email_hash=hashed,
                status="Gönderildi"
            )
            submission.original_pdf = pdf_file
            submission.save()
            messages.success(request, f"Makaleniz yüklendi. Takip numaranız: {tracking}")
            # Yönlendirme yerine direkt upload_success şablonunu render ediyoruz:
            return render(request, 'upload_success.html', {'tracking_number': tracking})
        else:
            messages.error(request, "Lütfen formdaki hataları düzeltin.")
    else:
        form = UploadForm()
    return render(request, 'upload_paper.html', {'form': form})

def status_view(request):
    submission_found = None
    if request.method == 'POST':
        form = StatusForm(request.POST)
        if form.is_valid():
            tnum = form.cleaned_data['tracking_number']
            email = form.cleaned_data['email']
            hashed = hash_email(email)
            try:
                sub = Submission.objects.get(tracking_number=tnum)
                if sub.email_hash == hashed:
                    submission_found = sub
                else:
                    messages.error(request, "Bilgiler hatalı.")
            except Submission.DoesNotExist:
                messages.error(request, "Makale bulunamadı.")
    else:
        form = StatusForm()
    return render(request, 'status.html', {'form': form, 'submission': submission_found})

def send_message(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('status')
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            sender_email = form.cleaned_data['email']
            content = form.cleaned_data['content']
            Message.objects.create(
                submission=sub,
                sender='user',
                sender_email=sender_email,
                content=content
            )
            Log.objects.create(submission=sub, action=f"Kullanıcı mesaj gönderdi: {sender_email}")
            messages.success(request, "Mesaj gönderildi.")
            return redirect('submission_messages', tracking_number=tracking_number)
    else:
        form = MessageForm()
    return render(request, 'send_message.html', {'form': form, 'submission': sub})

def submission_messages(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('status')
    msgs = sub.messages.all().order_by('-timestamp')
    return render(request, 'submission_messages.html', {'submission': sub, 'msgs': msgs})

def revise_paper(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('status')
    if sub.status != "Revize Gerekli":
        messages.error(request, "Bu makale için revize talep edilmedi.")
        return redirect('status')
    if request.method == 'POST':
        form = ReviseForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data['pdf_file']
            sub.revised_pdf = pdf_file
            sub.status = "Revize"
            sub.save()
            Log.objects.create(submission=sub, action="Kullanıcı revize makale yükledi.")
            messages.success(request, "Revize edilmiş makale yüklendi.")
            return redirect('status')
    else:
        form = ReviseForm()
    return render(request, 'revise_paper.html', {'form': form, 'submission': sub})

# YÖNETİCİ (Editör) Süreci
def editor_dashboard(request):
    subs = Submission.objects.all().order_by('-timestamp')
    return render(request, 'admin_panel.html', {'submissions': subs})

def extract_keywords_view(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    pdf_path = sub.revised_pdf.path if sub.revised_pdf else sub.original_pdf.path
    kws = extract_keywords_from_pdf_nlp(pdf_path)
    
    if kws:
        sub.extracted_keywords = ", ".join(kws)
        # Domain eşlemesi (örneğin, domain isimleri veya alt konuları ile eşleştirme)
        for d in Domain.objects.all():
            domain_name_lower = d.name.lower()
            subtopics_lower = [s.strip().lower() for s in d.subtopics.split(',')]
            for kw in kws:
                kw_lower = kw.lower()
                if kw_lower in domain_name_lower or any(kw_lower in st for st in subtopics_lower):
                    sub.domains.add(d)
        sub.save()
        Log.objects.create(submission=sub, action="Anahtar kelimeler çıkarıldı ve domain atandı.")
        return render(request, 'extracted_keywords.html', {'submission': sub, 'keywords': kws})
    else:
        messages.info(request, "Anahtar kelime bulunamadı.")
        return redirect('editor_dashboard')
    
def anonymize_view(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('editor_dashboard')
    input_path = sub.revised_pdf.path if sub.revised_pdf else sub.original_pdf.path
    filename = os.path.basename(input_path)
    output_path = os.path.join(settings.MEDIA_ROOT, 'anonymized', f"anon_{filename}")
    success = anonymize_pdf(input_path, output_path)
    if success:
        sub.anonymized_pdf.name = f"anonymized/anon_{filename}"
        sub.status = "Anonimleştirildi"
        sub.save()
        Log.objects.create(submission=sub, action="Makale anonimleştirildi.")
        messages.success(request, "Makale anonimleştirildi.")
    else:
        messages.error(request, "Anonimleştirme sırasında hata oluştu.")
    return redirect('editor_dashboard')

def assign_reviewer(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('editor_dashboard')
    matching_reviewers = Reviewer.objects.filter(interests__in=sub.domains.all()).distinct()
    if request.method == 'POST':
        reviewer_id = request.POST.get('reviewer_id')
        if reviewer_id:
            try:
                rev = Reviewer.objects.get(id=reviewer_id)
                sub.reviewer_assigned = rev.email
                sub.status = "Hakeme Atandı"
                sub.save()
                Log.objects.create(submission=sub, action=f"Hakeme atandı: {rev.email}")
                messages.success(request, f"{rev.name} adlı hakeme atandı.")
                return redirect('editor_dashboard')
            except Reviewer.DoesNotExist:
                messages.error(request, "Seçilen hakem bulunamadı.")
    return render(request, 'assign_reviewer.html', {
        'submission': sub,
        'matching_reviewers': matching_reviewers
    })

def request_revision(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('editor_dashboard')
    if sub.status != "Değerlendirildi":
        messages.error(request, "Makale henüz hakem tarafından değerlendirilmemiş.")
        return redirect('editor_dashboard')
    sub.status = "Revize Gerekli"
    sub.save()
    Log.objects.create(submission=sub, action="Editör revizyon istedi (Revize Gerekli).")
    messages.success(request, "Makale için revize talep edildi.")
    return redirect('editor_dashboard')
from django.http import FileResponse

def view_pdf(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('editor_dashboard')
    # Revize edilmiş dosya varsa onu, yoksa orijinal dosyayı açar.
    pdf_path = sub.revised_pdf.path if sub.revised_pdf else sub.original_pdf.path
    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

def reply_to_message(request, message_id):
    from .forms import ReplyForm  # Eğer ayrı dosyada tanımlıysa
    try:
        original_msg = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        messages.error(request, "Mesaj bulunamadı.")
        return redirect('editor_messages')
    submission = original_msg.submission
    if request.method == 'POST':
        form = ReplyForm(request.POST)
        if form.is_valid():
            reply_content = form.cleaned_data['content']
            # Yeni mesaj kaydı: Gönderen editör
            Message.objects.create(
                submission=submission,
                sender='editor',
                sender_email='editor@example.com',  # Editörün e-posta adresini belirleyin
                content=reply_content
            )
            Log.objects.create(submission=submission, action="Editör mesaj cevabı gönderdi.")
            messages.success(request, "Cevap mesajı gönderildi.")
            return redirect('editor_messages')
    else:
        form = ReplyForm()
    return render(request, 'reply_message.html', {
        'form': form,
        'original_msg': original_msg
    })

def finalize_view(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('editor_dashboard')
    if sub.status != "Değerlendirildi":
        messages.error(request, "Hakem değerlendirmesi bitmeden final oluşturulamaz.")
        return redirect('editor_dashboard')
    if not sub.anonymized_pdf or not sub.review:
        messages.error(request, "Anonimleştirilmiş PDF veya hakem değerlendirmesi yok.")
        return redirect('editor_dashboard')
    anon_path = sub.anonymized_pdf.path
    final_filename = f"final_{os.path.basename(anon_path)}"
    final_path = os.path.join(settings.MEDIA_ROOT, 'final', final_filename)
    success = merge_review_comments(anon_path, sub.review, final_path)
    if success:
        sub.final_pdf.name = f"final/{final_filename}"
        sub.status = "Final"
        sub.save()
        Log.objects.create(submission=sub, action="Final PDF oluşturuldu (Yazar bilgileri geri yüklendi).")
        messages.success(request, "Final PDF oluşturuldu.")
    else:
        messages.error(request, "Final PDF oluşturulurken hata oluştu.")
    return redirect('editor_dashboard')

def editor_logs(request):
    logs = Log.objects.all().order_by('-timestamp')
    return render(request, 'editor_logs.html', {'logs': logs})

def editor_messages(request):
    all_msgs = Message.objects.all().order_by('-timestamp')
    return render(request, 'editor_messages.html', {'all_msgs': all_msgs})

# HAKEM (Değerlendirici) Süreci
def reviewer_dashboard(request):
    subs = Submission.objects.filter(status__in=["Hakeme Atandı","Değerlendirildi"]).order_by('-timestamp')
    return render(request, 'reviewer_panel.html', {'submissions': subs})

def review_view(request, tracking_number):
    try:
        sub = Submission.objects.get(tracking_number=tracking_number)
    except Submission.DoesNotExist:
        messages.error(request, "Makale bulunamadı.")
        return redirect('reviewer_dashboard')
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            sub.review = form.cleaned_data['review_text']
            sub.status = "Değerlendirildi"
            sub.save()
            Log.objects.create(submission=sub, action="Hakem değerlendirme yaptı.")
            messages.success(request, "Değerlendirme kaydedildi.")
            return redirect('reviewer_dashboard')
    else:
        form = ReviewForm()
    return render(request, 'review.html', {'submission': sub, 'form': form})

# papers/views.py
from django.shortcuts import render, redirect, get_object_or_404
from .models import Submission
from .forms import AnonymizeOptionsForm
from .anonymization import anonymize_pdf, merge_review_comments  # merge_review_comments artık tanımlı

def anonymize_view(request, tracking_number):
    submission = get_object_or_404(Submission, tracking_number=tracking_number)
    
    # Orijinal PDF yolunu alıyoruz
    input_path = submission.original_pdf.path
    # Anonimleştirilmiş PDF için bir output path belirleyin (örneğin, media/anonymized klasörü içinde)
    output_path = submission.anonymized_pdf.path if submission.anonymized_pdf else input_path.replace("uploads", "anonymized")
    
    if request.method == "POST":
        form = AnonymizeOptionsForm(request.POST)
        if form.is_valid():
            options = form.cleaned_data
            # Anonymize işlemini çağırıyoruz
            success = anonymize_pdf(input_path, output_path, options)
            if success:
                submission.status = "Anonimleştirildi"
                submission.anonymized_pdf.name = output_path.split("media/")[-1]
                submission.save()
                return redirect("editor_dashboard")  # Yönetici paneline yönlendirme
    else:
        form = AnonymizeOptionsForm()
    
    return render(request, "anonymize_options.html", {"form": form, "submission": submission})

from django.shortcuts import render, redirect, get_object_or_404
from .models import Submission

def anonymize_options_view(request, tracking_number):
    submission = get_object_or_404(Submission, tracking_number=tracking_number)
    
    if request.method == 'POST':
        # Checkbox’ların durumu
        anon_name = 'anon_name' in request.POST
        anon_contact = 'anon_contact' in request.POST
        anon_institution = 'anon_institution' in request.POST
        
        # Seçilenlere göre anonimleştirme yapın
        # Örneğin, anonymize_pdf(submission, anon_name, anon_contact, anon_institution)
        
        return redirect('editor_dashboard')
    
    # GET isteğinde formu göster
    return render(request, 'anonymize_options.html', {
        'submission': submission,
    })
