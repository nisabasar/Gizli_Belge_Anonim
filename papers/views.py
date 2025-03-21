import os
import hashlib
import uuid
import json

from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse

from .models import Submission, Log, Message, Domain, Reviewer, Subtopic
from .forms import (
    UploadForm, ReviseForm, StatusForm, ReviewForm,
    MessageForm, ReplyForm, AnonymizeOptionsForm
)
from .anonymization import anonymize_pdf, merge_and_restore, merge_review_comments, restore_original_fields
from .nlp_utils import extract_keywords_from_pdf_advanced as extract_keywords_from_pdf_nlp


def generate_tracking_number():
    return str(uuid.uuid4())[:8]


def hash_email(email):
    return hashlib.sha256(email.encode('utf-8')).hexdigest()


# --- KULLANICI (Yazar) Süreci ---
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
            Log.objects.create(submission=submission, action="Makale yüklendi")
            messages.success(request, f"Makaleniz yüklendi. Takip numaranız: {tracking}")
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
                    messages.error(request, "E-posta adresi bu makaleyle eşleşmiyor.")
            except Submission.DoesNotExist:
                messages.error(request, "Makale bulunamadı.")
    else:
        form = StatusForm()
    return render(request, 'status.html', {'form': form, 'submission': submission_found})


def send_message(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
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
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    msgs = sub.messages.all().order_by('-timestamp')
    return render(request, 'submission_messages.html', {'submission': sub, 'msgs': msgs})


def revise_paper(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
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
            Log.objects.create(submission=sub, action="Kullanıcı revize makale yükledi")
            messages.success(request, "Revize edilmiş makale yüklendi.")
            return redirect('status')
    else:
        form = ReviseForm()
    return render(request, 'revise_paper.html', {'form': form, 'submission': sub})


# --- YÖNETİCİ (Editör) Süreci ---
def editor_dashboard(request):
    subs = Submission.objects.all().order_by('-timestamp')
    return render(request, 'admin_panel.html', {'submissions': subs})


def extract_keywords_view(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    pdf_path = sub.revised_pdf.path if sub.revised_pdf else sub.original_pdf.path
    kws = extract_keywords_from_pdf_nlp(pdf_path)
    if kws:
        sub.extracted_keywords = ", ".join(kws)
        sub.save()
        Log.objects.create(submission=sub, action="Anahtar kelimeler çıkarıldı")
        messages.success(request, "Anahtar kelimeler çıkarıldı.")
        return render(request, 'extracted_keywords.html', {'submission': sub, 'keywords': kws})
    else:
        messages.info(request, "Anahtar kelime bulunamadı.")
        return redirect('editor_dashboard')


def anonymize_view(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    input_path = sub.revised_pdf.path if sub.revised_pdf else sub.original_pdf.path
    filename = os.path.basename(input_path)
    output_path = os.path.join(settings.MEDIA_ROOT, 'anonymized', f"anon_{filename}")

    if request.method == "POST":
        form = AnonymizeOptionsForm(request.POST)
        print("DEBUG: POST geldi, form oluşturuldu.")

        if form.is_valid():
            print("DEBUG: form.is_valid() = True")

            # Formdan gelen değerler
            options = {
                'anonymize_name': form.cleaned_data['anonymize_name'],
                'anonymize_contact': form.cleaned_data['anonymize_contact'],
                'anonymize_institution': form.cleaned_data['anonymize_institution'],
                'blur_images': True  # Fotoğraf bulanıklaştırma da eklendi
            }
            print("DEBUG: Gelen options =", options)

            # Anonimleştirme
            regions = anonymize_pdf(input_path, output_path, options)
            print("DEBUG: anonymize_pdf regions =", regions)

            if regions is not None:
                sub.anonymized_pdf.name = os.path.join('anonymized', f"anon_{filename}")
                sub.status = "Anonimleştirildi"
                # (Dilerseniz 'regions' verisini kaydedebilirsiniz)
                sub.anonymized_data = json.dumps(regions)
                sub.save()
                Log.objects.create(submission=sub, action="Makale anonimleştirildi")

                messages.success(request, f"Makale anonimleştirildi! Bulunan alan sayısı: {len(regions)}")
                return redirect('editor_dashboard')
            else:
                messages.error(request, "Anonimleştirme sırasında hata oluştu (regions is None).")
        else:
            print("DEBUG: form.is_valid() = False")
            messages.error(request, "Form doğrulama hatası!")
    else:
        form = AnonymizeOptionsForm()

    return render(request, 'anonymize_options.html', {
        'form': form,
        'submission': sub
    })


def assign_reviewer(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    all_subtopics = Subtopic.objects.all()
    step = 1
    chosen_subtopic_ids = []
    matching_reviewers = Reviewer.objects.none()

    if request.method == 'POST':
        step_value = request.POST.get('step')
        if step_value == '1':
            chosen_subtopic_ids = request.POST.getlist('chosen_subtopics')
            if chosen_subtopic_ids:
                subtopic_qs = Subtopic.objects.filter(id__in=chosen_subtopic_ids)
                matching_reviewers = Reviewer.objects.filter(interests__in=subtopic_qs).distinct()
            step = 2
        elif step_value == '2':
            chosen_subtopic_ids = request.POST.getlist('chosen_subtopics')
            reviewer_id = request.POST.get('reviewer_id')
            if reviewer_id:
                rev = get_object_or_404(Reviewer, id=reviewer_id)
                sub.reviewer = rev
                sub.status = "Hakeme Atandı"
                sub.save()
                Log.objects.create(submission=sub, action=f"Hakeme atandı: {rev.name}")
                messages.success(request, f"{rev.name} adlı hakeme atandı.")
                return redirect('editor_dashboard')
            else:
                messages.error(request, "Lütfen bir hakem seçiniz.")
                step = 2
                subtopic_qs = Subtopic.objects.filter(id__in=chosen_subtopic_ids)
                matching_reviewers = Reviewer.objects.filter(interests__in=subtopic_qs).distinct()

    context = {
        'submission': sub,
        'all_subtopics': all_subtopics,
        'step': step,
        'matching_reviewers': matching_reviewers,
        'chosen_subtopic_ids': chosen_subtopic_ids,
    }
    return render(request, 'assign_reviewer.html', context)


def reviewer_list(request):
    reviewers = Reviewer.objects.all()
    return render(request, 'reviewer_list.html', {'reviewers': reviewers})


def reviewer_detail(request, reviewer_id):
    reviewer = get_object_or_404(Reviewer, pk=reviewer_id)
    submissions = Submission.objects.filter(reviewer=reviewer)
    return render(request, 'reviewer_detail.html', {'reviewer': reviewer, 'submissions': submissions})


def request_revision(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if sub.status != "Değerlendirildi":
        messages.error(request, "Makale henüz hakem tarafından değerlendirilmemiş.")
        return redirect('editor_dashboard')
    sub.status = "Revize Gerekli"
    sub.save()
    Log.objects.create(submission=sub, action="Editör revizyon istedi (Revize Gerekli)")
    messages.success(request, "Makale için revize talep edildi.")
    return redirect('editor_dashboard')




def reply_to_message(request, message_id):
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
            Message.objects.create(
                submission=submission,
                sender='editor',
                sender_email='editor@example.com',
                content=reply_content
            )
            Log.objects.create(submission=submission, action="Editör mesaj cevabı gönderdi")
            messages.success(request, "Cevap mesajı gönderildi.")
            return redirect('editor_messages')
    else:
        form = ReplyForm()
    return render(request, 'reply_message.html', {'form': form, 'original_msg': original_msg})


def finalize_view(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if sub.status != "Değerlendirildi":
        messages.error(request, "Hakem değerlendirmesi bitmeden final oluşturulamaz.")
        return redirect('editor_dashboard')
    if not sub.reviewed_pdf or not sub.anonymized_data:
        messages.error(request, "Değerlendirilmiş makale veya anonimleştirilmiş bilgiler eksik.")
        return redirect('editor_dashboard')
    
    reviewed_path = sub.reviewed_pdf.path
    final_filename = f"final_{os.path.basename(reviewed_path)}"
    final_path = os.path.join(settings.MEDIA_ROOT, 'final', final_filename)
    
    try:
        regions = json.loads(sub.anonymized_data)
    except Exception as e:
        messages.error(request, f"Anonimleştirilmiş bilgileri okuyamadık: {e}")
        return redirect('editor_dashboard')
    
    # restore_original_fields çağrısına categories_to_restore parametresini ekledik:
    success = restore_original_fields(
        input_pdf_path=reviewed_path,
        original_pdf_path=sub.original_pdf.path,
        regions=regions,
        categories_to_restore=["name", "contact", "institution", "image"],  # "image" eklendi
        output_pdf_path=final_path
    )


    
    if success:
        sub.final_pdf.name = os.path.join('final', final_filename)
        sub.status = "Final"
        sub.final_sent = False
        sub.save()
        Log.objects.create(submission=sub, action="Final PDF oluşturuldu (henüz gönderilmedi)")
        messages.success(request, "Final PDF oluşturuldu. Lütfen 'Final PDF Gönder' butonuna basınız.")
    else:
        messages.error(request, "Restore işlemi sırasında hata oluştu.")
    return redirect('editor_dashboard')


def send_final_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if not sub.final_pdf:
        messages.error(request, "Final PDF oluşturulmamış.")
        return redirect('editor_dashboard')
    sub.final_sent = True
    sub.save()
    Log.objects.create(submission=sub, action="Final PDF gönderildi (yazara iletildi)")
    messages.success(request, "Final PDF yazara gönderildi.")
    return redirect('editor_dashboard')


def request_revision_user(request, tracking_number):
    """
    Yazar, final PDF'yi gördükten sonra 'Revize Gerekli' butonuna basarak makaleyi
    tekrar revize sürecine döndürür.
    """
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if sub.status != "Final":
        messages.error(request, "Yalnızca final durumundaki makalelerde revize talep edebilirsiniz.")
        return redirect('status')
    sub.status = "Revize Gerekli"
    sub.final_sent = False
    sub.save()
    Log.objects.create(submission=sub, action="Yazar revize talep etti (Final aşamasından geri)")
    messages.success(request, "Revize talebiniz alındı. Makale yeniden revize sürecine girdi.")
    return redirect('status')


def view_final_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if not sub.final_pdf:
        messages.error(request, "Final PDF yok.")
        return redirect('editor_dashboard')
    pdf_path = sub.final_pdf.path
    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')


def editor_logs(request):
    logs = Log.objects.all().order_by('-timestamp')
    return render(request, 'editor_logs.html', {'logs': logs})


def editor_messages(request):
    all_msgs = Message.objects.all().order_by('-timestamp')
    return render(request, 'editor_messages.html', {'all_msgs': all_msgs})


# --- HAKEM (Değerlendirici) Süreci ---
def reviewer_panel(request):
    reviewers = Reviewer.objects.all().order_by('name')
    chosen_reviewer = None
    submissions = None
    if request.method == 'POST':
        reviewer_id = request.POST.get('reviewer_id')
        if reviewer_id:
            chosen_reviewer = get_object_or_404(Reviewer, pk=reviewer_id)
            submissions = Submission.objects.filter(reviewer=chosen_reviewer).order_by('-timestamp')
    return render(request, 'reviewer_panel.html', {
        'reviewers': reviewers,
        'chosen_reviewer': chosen_reviewer,
        'submissions': submissions,
    })


def review_view(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if sub.status != "Hakeme Atandı":
        messages.error(request, "Bu makale şu an değerlendirilemez (Hakeme Atanmadı).")
        return redirect('reviewer_panel')
    if not sub.anonymized_pdf:
        messages.error(request, "Anonimleştirilmiş PDF bulunamadı.")
        return redirect('reviewer_panel')
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review_text = form.cleaned_data['review_text']
            additional_notes = form.cleaned_data.get('additional_notes', '')
            combined_review = review_text
            if additional_notes:
                combined_review += "\n\nEk Açıklamalar:\n" + additional_notes
            anon_pdf_path = sub.anonymized_pdf.path
            reviewed_filename = f"reviewed_{os.path.basename(anon_pdf_path)}"
            reviewed_path = os.path.join(settings.MEDIA_ROOT, 'reviewed', reviewed_filename)
            success = merge_review_comments(anon_pdf_path, combined_review, reviewed_path)
            if success:
                sub.review = combined_review
                sub.reviewed_pdf.name = os.path.join('reviewed', reviewed_filename)
                sub.status = "Değerlendirildi"
                sub.save()
                reviewer_name = sub.reviewer.name if sub.reviewer else "Bilinmiyor"
                Log.objects.create(submission=sub, action=f"Hakem {reviewer_name} değerlendirme yaptı")
                messages.success(request, "Değerlendirme kaydedildi ve Değerlendirilmiş Makale oluşturuldu.")
            else:
                messages.error(request, "PDF'e değerlendirme eklenirken hata oluştu.")
            return redirect('reviewer_panel')
    else:
        form = ReviewForm()
    return render(request, 'review.html', {'submission': sub, 'form': form})


def reassign_reviewer(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    all_reviewers = Reviewer.objects.all()
    if request.method == 'POST':
        reviewer_id = request.POST.get('reviewer_id')
        if reviewer_id:
            new_reviewer = get_object_or_404(Reviewer, id=reviewer_id)
            sub.reviewer = new_reviewer
            sub.status = "Hakeme Atandı"
            sub.save()
            Log.objects.create(submission=sub, action=f"Hakem değiştirildi. Yeni hakem: {new_reviewer.name}")
            messages.success(request, f"Hakem {new_reviewer.name} olarak değiştirildi.")
            return redirect('editor_dashboard')
        else:
            messages.error(request, "Lütfen bir hakem seçiniz.")
    context = {
        'submission': sub,
        'reviewers': all_reviewers
    }
    return render(request, 'reassign_reviewer.html', context)


def view_reviewed_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if not sub.reviewed_pdf:
        messages.error(request, "Değerlendirilmiş Makale bulunamadı.")
        return redirect('editor_dashboard')
    pdf_path = sub.reviewed_pdf.path
    try:
        return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
        messages.error(request, f"PDF açılamadı: {e}")
        return redirect('editor_dashboard')


def restore_original(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if request.method == 'POST':
        form = AnonymizeOptionsForm(request.POST)
        if form.is_valid():
            selected = []
            if form.cleaned_data.get('anonymize_name'):
                selected.append("name")
            if form.cleaned_data.get('anonymize_contact'):
                selected.append("contact")
            if form.cleaned_data.get('anonymize_institution'):
                selected.append("institution")
            if not selected:
                messages.error(request, "Hiçbir alan seçilmedi!")
                return redirect('editor_dashboard')
            if not sub.anonymized_data:
                messages.error(request, "Anonimleştirme bilgileri bulunamadı.")
                return redirect('editor_dashboard')
            try:
                regions = json.loads(sub.anonymized_data)
            except Exception as e:
                messages.error(request, f"Anonimleştirilmiş bilgileri okuyamadık: {e}")
                return redirect('editor_dashboard')
            
            success = restore_original_fields(
                input_pdf_path=sub.anonymized_pdf.path,
                original_pdf_path=sub.original_pdf.path,
                regions=regions,
                categories_to_restore=selected,  # Seçilen kategoriler gönderiliyor
                output_pdf_path=sub.anonymized_pdf.path
            )
            
            if success:
                sub.restored = True
                sub.status = "Düzenlenmiş"
                sub.save()
                Log.objects.create(submission=sub, action="Orijinal bilgiler geri yüklendi")
                messages.success(request, "Seçili alanlar orijinal hale getirildi (kısmi restore).")
                return redirect('editor_dashboard')
            else:
                messages.error(request, "Restore işlemi sırasında hata oluştu.")
                return redirect('editor_dashboard')
    else:
        form = AnonymizeOptionsForm()
    return render(request, 'restore_options.html', {'form': form, 'submission': sub})

def view_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if sub.anonymized_pdf:
        pdf_path = sub.anonymized_pdf.path
    else:
        pdf_path = sub.original_pdf.path
    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

def view_restored_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if not sub.restored:
        messages.error(request, "Restore işlemi yapılmamış veya başarısız.")
        return redirect('editor_dashboard')
    pdf_path = sub.anonymized_pdf.path
    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')


def download_anonymized_pdf(request, tracking_number):
    sub = get_object_or_404(Submission, tracking_number=tracking_number)
    if not sub.anonymized_pdf:
        messages.error(request, "Anonimleştirilmiş PDF bulunamadı.")
        return redirect('editor_dashboard')
    pdf_path = sub.anonymized_pdf.path
    try:
        response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{sub.tracking_number}_anon.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"PDF indirilemedi: {e}")
        return redirect('editor_dashboard')


def clear_all_submissions(request):
    for sub in Submission.objects.all():
        if sub.original_pdf:
            sub.original_pdf.delete()
        if sub.revised_pdf:
            sub.revised_pdf.delete()
        if sub.anonymized_pdf:
            sub.anonymized_pdf.delete()
        if sub.final_pdf:
            sub.final_pdf.delete()
    Submission.objects.all().delete()
    Log.objects.all().delete()
    Message.objects.all().delete()
    messages.success(request, "Tüm makaleler, loglar ve mesajlar temizlendi.")
    return redirect('editor_dashboard')
