from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('makalesistemi/yukle/', views.upload_paper, name='upload_paper'),
    path('makaledurumsorgulama/', views.status_view, name='status'),
    path('makalesistemi/mesaj/<str:tracking_number>/', views.send_message, name='send_message'),
    path('makalesistemi/mesajlar/<str:tracking_number>/', views.submission_messages, name='submission_messages'),
    path('makalesistemi/revize/<str:tracking_number>/', views.revise_paper, name='revise_paper'),
    path('makalesistemi/yonetici/', views.editor_dashboard, name='editor_dashboard'),
    path('makalesistemi/yonetici/logs/', views.editor_logs, name='editor_logs'),
    path('makalesistemi/yonetici/messages/', views.editor_messages, name='editor_messages'),
    path('makalesistemi/yonetici/view_pdf/<str:tracking_number>/', views.view_pdf, name='view_pdf'),
    path('makalesistemi/yonetici/extract_keywords/<str:tracking_number>/', views.extract_keywords_view, name='extract_keywords_view'),
    path('makalesistemi/yonetici/anonymize/<str:tracking_number>/', views.anonymize_view, name='anonymize_view'),
    path('makalesistemi/yonetici/assign/<str:tracking_number>/', views.assign_reviewer, name='assign_reviewer'),
    path('makalesistemi/yonetici/request_revision/<str:tracking_number>/', views.request_revision, name='request_revision'),
    path('makalesistemi/yonetici/finalize/<str:tracking_number>/', views.finalize_view, name='finalize_view'),
    path('makalesistemi/yonetici/reply/<int:message_id>/', views.reply_to_message, name='reply_to_message'),
    path('makalesistemi/yonetici/download_anon/<str:tracking_number>/', views.download_anonymized_pdf, name='download_anonymized_pdf'),
    path('makalesistemi/yonetici/restore/<str:tracking_number>/', views.restore_original, name='restore_original'),
    path('makalesistemi/yonetici/clear_all/', views.clear_all_submissions, name='clear_all_submissions'),

    # Hakemlerin makaleyi değerlendirdiği kısım
    path('makalesistemi/degerlendirici/review/<str:tracking_number>/', views.review_view, name='review_view'),
    
    # Restore edilmiş PDF gösterme
    path('makalesistemi/yonetici/view_restored/<str:tracking_number>/', views.view_restored_pdf, name='view_restored_pdf'),

    # Asıl PDF görüntüleme (orijinal ya da anonymized)
    path('makalesistemi/yonetici/view_pdf/<str:tracking_number>/', views.view_pdf, name='view_pdf'),

    path('makalesistemi/yonetici/view_final/<str:tracking_number>/', views.view_final_pdf, name='view_final_pdf'),

    # HAKEM PANELI (Dropdown yaklaşımı)
    path('makalesistemi/degerlendirici/', views.reviewer_panel, name='reviewer_panel'),
    
    path('makalesistemi/yonetici/view_reviewed/<str:tracking_number>/', views.view_reviewed_pdf, name='view_reviewed_pdf'),

    path('makalesistemi/yonetici/send_final/<str:tracking_number>/', views.send_final_pdf, name='send_final_pdf'),


]
