from django.contrib import admin
from .models import Domain, Reviewer, Log, Message, Subtopic

# Subtopic'i Domain admin sayfasına inline ekleyeceğiz
class SubtopicInline(admin.TabularInline):
    model = Subtopic
    extra = 1  # Yeni domain eklerken, 1 boş satır göstersin

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    """
    Domain sayfasında, alt başlıklar (Subtopic) inline olarak düzenlenebilir.
    """
    inlines = [SubtopicInline]
    list_display = ('name',)

@admin.register(Subtopic)
class SubtopicAdmin(admin.ModelAdmin):
    """
    İsterseniz Subtopic için de ayrı bir admin görünümü olabilir,
    fakat Domain üzerinden inline olarak eklemek genelde yeterli.
    """
    list_display = ('domain', 'name')
    list_filter = ('domain',)

@admin.register(Reviewer)
class ReviewerAdmin(admin.ModelAdmin):
    """
    Hakem admin sayfasında, interests (subtopics) M2M alanını
    birden fazla seçim yapabileceği bir widgetla gösteriyoruz.
    """
    list_display = ('name', 'email')
    filter_horizontal = ('interests',)  # Daha kullanışlı bir çoklu seçim widget'ı

admin.site.register(Log)
admin.site.register(Message)
