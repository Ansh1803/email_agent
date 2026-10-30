
from django.contrib import admin
from .models import GmailAccount, EmailMessage, EmailSummary, ReplyDraft


@admin.register(GmailAccount)
class GmailAccountAdmin(admin.ModelAdmin):
    list_display = ("email_address", "user", "is_connected", "created_at")
    list_filter = ("is_connected", "created_at")
    search_fields = ("email_address", "user__username")


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender_email", "account", "received_at", "is_read")
    list_filter = ("is_read", "received_at")
    search_fields = ("subject", "sender_email", "body")


@admin.register(EmailSummary)
class EmailSummaryAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("summary",)


@admin.register(ReplyDraft)
class ReplyDraftAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "created_at", "sent_at")
    list_filter = ("status", "created_at")
    search_fields = ("reply_body",)
