from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/profiles/', include('profiles.urls')),
    path('api/v1/listings/', include('listings.urls')),
    path('api/v1/matches/', include('matching.urls')),
    path('api/v1/moderation/', include('moderation.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/verification/', include('verification.urls')),
    path('api/v1/admin/', include('admin_management.urls')),
    path('api/v1/notifications/', include('notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
