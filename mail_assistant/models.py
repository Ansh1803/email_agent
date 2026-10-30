
from django.conf import settings
from django.db import models


class GmailAccount(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gmail_accounts"
    )
    email_address = models.EmailField()
    encrypted_credentials = models.TextField()
    is_connected = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "email_address"],
                name="unique_gmail_account_per_user"
            )
        ]

    def __str__(self):
        return self.email_address


class EmailMessage(models.Model):
    account = models.ForeignKey(
        GmailAccount,
        on_delete=models.CASCADE,
        related_name="emails"
    )
    gmail_message_id = models.CharField(max_length=255)
    thread_id = models.CharField(max_length=255, blank=True)
    sender_email = models.EmailField()
    sender_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    snippet = models.TextField(blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "gmail_message_id"],
                name="unique_gmail_message_per_account"
            )
        ]
        ordering = ["-received_at", "-created_at"]

    def __str__(self):
        return self.subject or f"Email from {self.sender_email}"


class EmailSummary(models.Model):
    email = models.OneToOneField(
        EmailMessage,
        on_delete=models.CASCADE,
        related_name="ai_summary"
    )
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary: {self.email.subject}"


class ReplyDraft(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        SENT = "SENT", "Sent"
        REJECTED = "REJECTED", "Rejected"

    email = models.ForeignKey(
        EmailMessage,
        on_delete=models.CASCADE,
        related_name="reply_drafts"
    )
    reply_body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Reply to: {self.email.subject} ({self.status})"
