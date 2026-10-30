import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .models import GmailAccount, EmailMessage , EmailSummary,ReplyDraft
from .services.ai_service import generate_email_reply
from .services.google_oauth import send_email_reply
from .services.google_oauth import (
    create_oauth_flow,
    encrypt_credentials,
    get_gmail_profile,
    fetch_recent_messages,
    extract_email_data,
)
from .services.ai_service import summarize_email as generate_summary
from django.utils import timezone

from django.contrib.auth import get_user_model

# --------------------------------------------------
# HOME / LOGIN
# --------------------------------------------------

def home(request):
    return render(request, "mail_assistant/dashboard.html")


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

def dashboard(request):
    try:
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        accounts = GmailAccount.objects.filter(
            user=fixed_user,
            is_connected=True
        )

        emails = EmailMessage.objects.filter(
            account__user=fixed_user
        ).select_related(
            "account", "ai_summary"
        ).prefetch_related(
            "reply_drafts"
        ).order_by(
            "-received_at", "-created_at"
        )[:50]

    except User.DoesNotExist:
        accounts = GmailAccount.objects.none()
        emails = EmailMessage.objects.none()
        messages.error(
            request,
            "The configured application user was not found."
        )

    return render(
        request,
        "mail_assistant/dashboard.html",
        {
            "accounts": accounts,
            "emails": emails,
        }
    )

# --------------------------------------------------
# CONNECT GMAIL
# --------------------------------------------------


def gmail_connect(request):
    try:
        flow = create_oauth_flow()

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )

        # Save OAuth state and PKCE verifier in the session.
        request.session["gmail_oauth_state"] = state
        request.session["gmail_code_verifier"] = flow.code_verifier

        return redirect(authorization_url)

    except Exception:
        traceback.print_exc()

        messages.error(
            request,
            "Could not start Gmail authorization. Check the terminal for details."
        )
        return redirect("dashboard")


# --------------------------------------------------
# GMAIL OAUTH CALLBACK
# --------------------------------------------------

def gmail_oauth_callback(request):
    saved_state = request.session.get("gmail_oauth_state")
    received_state = request.GET.get("state")

    # Validate OAuth state to protect against CSRF.
    if not saved_state or received_state != saved_state:
        messages.error(
            request,
            "Invalid OAuth state. Please start the Gmail connection again."
        )
        return redirect("dashboard")

    # Handle authorization cancellation or denial.
    if request.GET.get("error"):
        request.session.pop("gmail_oauth_state", None)
        request.session.pop("gmail_code_verifier", None)

        messages.error(
            request,
            "Gmail authorization was cancelled or denied."
        )
        return redirect("dashboard")

    try:
        # Create OAuth flow.
        flow = create_oauth_flow(state=saved_state)

        # Restore PKCE verifier.
        flow.code_verifier = request.session.get(
            "gmail_code_verifier"
        )

        if not flow.code_verifier:
            raise ValueError(
                "OAuth code verifier is missing. Please reconnect Gmail."
            )

        # Exchange authorization code.
        flow.fetch_token(
            authorization_response=request.build_absolute_uri()
        )

        credentials = flow.credentials

        # Get authorized Gmail account.
        profile = get_gmail_profile(credentials)
        email_address = profile["emailAddress"]

        # Encrypt Gmail credentials.
        encrypted_data = encrypt_credentials(credentials)

        # Use the fixed Django user instead of AnonymousUser.
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        # Save Gmail account.
        GmailAccount.objects.update_or_create(
            user=fixed_user,
            email_address=email_address,
            defaults={
                "encrypted_credentials": encrypted_data,
                "is_connected": True,
            }
        )

        # Clear temporary OAuth session data.
        request.session.pop("gmail_oauth_state", None)
        request.session.pop("gmail_code_verifier", None)

        messages.success(
            request,
            f"Gmail account {email_address} connected successfully!"
        )

    except Exception as exc:
        traceback.print_exc()

        messages.error(
            request,
            f"Gmail connection failed: {type(exc).__name__}: {exc}"
        )

    return redirect("dashboard")
# --------------------------------------------------
# SYNC INBOX
# --------------------------------------------------

@require_POST
def sync_inbox(request):
    try:
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        accounts = GmailAccount.objects.filter(
            user=fixed_user,
            is_connected=True
        )

        if not accounts.exists():
            messages.error(
                request,
                "No Gmail account is connected. Connect Gmail first."
            )
            return redirect("dashboard")

        total_processed = 0

        for account in accounts:
            # Fetch the latest 20 messages.
            gmail_messages = fetch_recent_messages(
                account,
                max_results=20
            )

            for gmail_message in gmail_messages:
                email_data = extract_email_data(gmail_message)

                # Save or update emails without duplicates.
                EmailMessage.objects.update_or_create(
                    account=account,
                    gmail_message_id=email_data["gmail_message_id"],
                    defaults={
                        "thread_id": email_data["thread_id"],
                        "sender_email": email_data["sender_email"],
                        "sender_name": email_data["sender_name"],
                        "subject": email_data["subject"],
                        "body": email_data["body"],
                        "snippet": email_data["snippet"],
                        "received_at": email_data["received_at"],
                        "is_read": email_data["is_read"],
                    }
                )

                total_processed += 1

        messages.success(
            request,
            f"Inbox sync completed. Processed {total_processed} emails."
        )

    except Exception:
        traceback.print_exc()

        messages.error(
            request,
            "Inbox sync failed. Check the server logs for details."
        )

    return redirect("dashboard")
@require_POST
def summarize_email_view(request, email_id):
    try:
        # Use the fixed Django user.
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        # Only access emails belonging to the fixed user.
        email = EmailMessage.objects.get(
            id=email_id,
            account__user=fixed_user
        )

        # Reuse an existing summary.
        summary, created = EmailSummary.objects.get_or_create(
            email=email,
            defaults={"summary": ""}
        )

        if not created and summary.summary:
            messages.info(
                request,
                "This email already has an AI summary."
            )
            return redirect("dashboard")

        # Generate summary using Groq.
        summary_text = generate_summary(
            subject=email.subject,
            sender=email.sender_email,
            body=email.body
        )

        summary.summary = summary_text
        summary.save(update_fields=["summary"])

        messages.success(
            request,
            "AI summary generated successfully."
        )

    except EmailMessage.DoesNotExist:
        messages.error(request, "Email not found.")

    except Exception:
        traceback.print_exc()
        messages.error(
            request,
            "Could not generate the summary. Check the server logs for details."
        )

    return redirect("dashboard")

@require_POST
def generate_reply_view(request, email_id):
    try:
        # Use the fixed Django user.
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        # Only access emails belonging to the fixed user.
        email = EmailMessage.objects.get(
            id=email_id,
            account__user=fixed_user
        )

        summary = getattr(email, "ai_summary", None)
        summary_text = summary.summary if summary else ""

        # Generate AI reply using Groq.
        reply_text = generate_email_reply(
            subject=email.subject,
            sender=email.sender_email,
            body=email.body,
            summary=summary_text
        )

        # Save reply draft.
        ReplyDraft.objects.create(
            email=email,
            reply_body=reply_text,
            status=ReplyDraft.Status.DRAFT
        )

        messages.success(
            request,
            "AI reply draft generated."
        )

    except EmailMessage.DoesNotExist:
        messages.error(request, "Email not found.")

    except Exception:
        traceback.print_exc()
        messages.error(
            request,
            "Could not generate the reply. Check server logs for details."
        )

    return redirect("dashboard")

@require_POST
def send_reply_view(request, draft_id):
    try:
        # Use the fixed Django user.
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        draft = ReplyDraft.objects.select_related(
            "email__account"
        ).get(
            id=draft_id,
            email__account__user=fixed_user
        )

        # Prevent accidental duplicate sends.
        if draft.status == ReplyDraft.Status.SENT:
            messages.warning(
                request,
                "This reply has already been sent."
            )
            return redirect("dashboard")

        if draft.status != ReplyDraft.Status.DRAFT:
            messages.error(
                request,
                "This draft is not ready to send."
            )
            return redirect("dashboard")

        email = draft.email
        account = email.account

        if not account.is_connected:
            messages.error(
                request,
                "Your Gmail account is not connected."
            )
            return redirect("dashboard")

        if not email.sender_email or "@" not in email.sender_email:
            messages.error(
                request,
                "The recipient email address is invalid."
            )
            return redirect("dashboard")

        # Send through Gmail API.
        result = send_email_reply(
            account=account,
            recipient=email.sender_email,
            subject=email.subject,
            body=draft.reply_body
        )

        # Update status after Gmail confirms success.
        draft.status = ReplyDraft.Status.SENT
        draft.sent_at = timezone.now()
        draft.save(
            update_fields=["status", "sent_at", "updated_at"]
        )

        messages.success(
            request,
            f"Reply sent successfully! Gmail message ID: {result.get('id')}"
        )

    except ReplyDraft.DoesNotExist:
        messages.error(request, "Reply draft not found.")

    except Exception:
        traceback.print_exc()
        messages.error(
            request,
            "Could not send the reply. Check the server logs for details."
        )

    return redirect("dashboard")

@require_POST
def update_reply_view(request, draft_id):
    try:
        # Use the fixed Django user.
        User = get_user_model()
        fixed_user = User.objects.get(username="ansh")

        draft = ReplyDraft.objects.get(
            id=draft_id,
            email__account__user=fixed_user
        )

        if draft.status != ReplyDraft.Status.DRAFT:
            messages.error(
                request,
                "Only unsent drafts can be edited."
            )
            return redirect("dashboard")

        updated_body = request.POST.get(
            "reply_body", ""
        ).strip()

        if not updated_body:
            messages.error(
                request,
                "Reply cannot be empty."
            )
            return redirect("dashboard")

        draft.reply_body = updated_body
        draft.save(
            update_fields=["reply_body", "updated_at"]
        )

        messages.success(
            request,
            "Reply draft updated successfully."
        )

    except ReplyDraft.DoesNotExist:
        messages.error(
            request,
            "Reply draft not found."
        )

    except Exception:
        traceback.print_exc()
        messages.error(
            request,
            "Could not update the reply. Check server logs."
        )

    return redirect("dashboard")

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import os

@csrf_exempt
def setup_app_user(request):
    if request.GET.get("key") != os.getenv("SETUP_SECRET"):
        return HttpResponse("Forbidden", status=403)

    User = get_user_model()

    user, created = User.objects.get_or_create(
        username="ansh",
        defaults={
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
    )

    return HttpResponse(
        "User created" if created else "User already exists"
    )