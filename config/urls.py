from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView
from mail_assistant.views import setup_app_user

urlpatterns = [
    path('admin/', admin.site.urls),

    path(
        'accounts/login/',
        LoginView.as_view(
            template_name='mail_assistant/login.html'
        ),
        name='login'
    ),

    path('', include('mail_assistant.urls')),

    path('accounts/', include('django.contrib.auth.urls')),
    path("setup-app-user/", setup_app_user),
]