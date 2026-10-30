from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path("dashboard/", views.dashboard, name="dashboard"),

    path(
        "gmail/connect/",
        views.gmail_connect,
        name="gmail_connect"
    ),

    path(
        "gmail/oauth/callback/",
        views.gmail_oauth_callback,
        name="gmail_oauth_callback"
    ),

    path(
        "gmail/sync/",
        views.sync_inbox,
        name="sync_inbox"
    ),

    path(
        "email/<int:email_id>/summarize/",
        views.summarize_email_view,
        name="summarize_email"
    ),

    path(
        "email/<int:email_id>/generate-reply/",
        views.generate_reply_view,
        name="generate_reply"
    ),
    path(
    "reply/<int:draft_id>/send/",
    views.send_reply_view,
    name="send_reply"
),
path(
    "reply/<int:draft_id>/update/",
    views.update_reply_view,
    name="update_reply"
),
]