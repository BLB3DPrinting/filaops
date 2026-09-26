"""
Email service for sending notifications

Handles SMTP email sending for:
- Password reset approval requests
- Password reset confirmation
- Order notifications
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# How long to wait for the SMTP server before giving up. Without a limit an
# unreachable host holds the caller for the operating system's connect
# timeout, which can be minutes.
SMTP_TIMEOUT_SECONDS = 10


class EmailService:
    """Service for sending emails via SMTP"""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME

    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """
        Send an email via SMTP

        Returns True if successful, False otherwise
        """
        if not self.user or not self.password:
            logger.warning("SMTP credentials not configured - email not sent")
            # Never log the body: these emails carry approval and reset links.
            logger.info(f"Would have sent email to {to_email}: {subject}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            # Add plain text version
            if text_body:
                msg.attach(MIMEText(text_body, "plain"))

            # Add HTML version
            msg.attach(MIMEText(html_body, "html"))

            # Connect and send
            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_password_reset_approval_request(
        self,
        admin_email: str,
        user_email: str,
        user_name: str,
        approval_token: str,
        frontend_url: str
    ) -> bool:
        """
        Send password reset approval request to admin

        Contains approve/deny links for the admin to click
        """
        approve_url = f"{frontend_url}/admin/password-reset/approve/{approval_token}"
        deny_url = f"{frontend_url}/admin/password-reset/deny/{approval_token}"

        subject = f"[FilaOps] Password Reset Request - {user_email}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; }}
                .user-info {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .buttons {{ margin-top: 20px; }}
                .btn {{ display: inline-block; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-right: 10px; }}
                .btn-approve {{ background: #22c55e; color: white; }}
                .btn-deny {{ background: #ef4444; color: white; }}
                .footer {{ padding: 15px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">Password Reset Request</h1>
                </div>
                <div class="content">
                    <p>A user has requested a password reset. Please review and approve or deny this request.</p>

                    <div class="user-info">
                        <p><strong>User:</strong> {user_name}</p>
                        <p><strong>Email:</strong> {user_email}</p>
                        <p><strong>Requested:</strong> Just now</p>
                    </div>

                    <p>Click one of the buttons below to respond:</p>

                    <div class="buttons">
                        <a href="{approve_url}" class="btn btn-approve">Approve Reset</a>
                        <a href="{deny_url}" class="btn btn-deny">Deny Request</a>
                    </div>

                    <p style="margin-top: 20px; font-size: 14px; color: #666;">
                        This request will expire in 24 hours if not acted upon.
                    </p>
                </div>
                <div class="footer">
                    <p>FilaOps - Admin Notification</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Password Reset Request

        A user has requested a password reset. Please review and approve or deny.

        User: {user_name}
        Email: {user_email}

        To APPROVE: {approve_url}
        To DENY: {deny_url}

        This request expires in 24 hours.

        --
        FilaOps
        """

        return self._send_email(admin_email, subject, html_body, text_body)

    def send_password_reset_approved(
        self,
        user_email: str,
        user_name: str,
        reset_token: str,
        frontend_url: str
    ) -> bool:
        """
        Send password reset link to user after admin approval
        """
        reset_url = f"{frontend_url}/reset-password/{reset_token}"

        subject = "[FilaOps] Your Password Reset Has Been Approved"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; }}
                .btn {{ display: inline-block; padding: 14px 28px; background: #2563eb; color: white; border-radius: 6px; text-decoration: none; font-weight: bold; }}
                .footer {{ padding: 15px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">Password Reset Approved</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>

                    <p>Your password reset request has been approved. Click the button below to set a new password:</p>

                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" class="btn">Reset My Password</a>
                    </p>

                    <p style="font-size: 14px; color: #666;">
                        This link will expire in 1 hour. If you didn't request this reset, please contact us immediately.
                    </p>

                    <p style="font-size: 12px; color: #999; margin-top: 20px;">
                        If the button doesn't work, copy and paste this link into your browser:<br>
                        <a href="{reset_url}">{reset_url}</a>
                    </p>
                </div>
                <div class="footer">
                    <p>BLB3D Printing</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Hi {user_name},

        Your password reset request has been approved.

        Click here to reset your password:
        {reset_url}

        This link expires in 1 hour.

        If you didn't request this, please contact us immediately.

        --
        FilaOps
        """

        return self._send_email(user_email, subject, html_body, text_body)

    def send_password_reset_denied(
        self,
        user_email: str,
        user_name: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Notify user that their password reset was denied
        """
        subject = "[FilaOps] Password Reset Request Denied"

        reason_text = reason or "Please contact support for assistance."

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #ef4444; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; }}
                .footer {{ padding: 15px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">Password Reset Denied</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>

                    <p>Your password reset request has been denied.</p>

                    <p><strong>Reason:</strong> {reason_text}</p>

                    <p>If you believe this is an error or need assistance, please contact us at {settings.BUSINESS_EMAIL}</p>
                </div>
                <div class="footer">
                    <p>BLB3D Printing</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Hi {user_name},

        Your password reset request has been denied.

        Reason: {reason_text}

        If you need assistance, please contact {settings.BUSINESS_EMAIL}

        --
        FilaOps
        """

        return self._send_email(user_email, subject, html_body, text_body)

    def send_password_reset_completed(
        self,
        user_email: str,
        user_name: str
    ) -> bool:
        """
        Confirm to user that their password was successfully changed
        """
        subject = "[FilaOps] Your Password Has Been Changed"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #22c55e; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; }}
                .footer {{ padding: 15px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">Password Changed Successfully</h1>
                </div>
                <div class="content">
                    <p>Hi {user_name},</p>

                    <p>Your password has been successfully changed.</p>

                    <p>If you did not make this change, please contact us immediately at {settings.BUSINESS_EMAIL}</p>
                </div>
                <div class="footer">
                    <p>BLB3D Printing</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Hi {user_name},

        Your password has been successfully changed.

        If you did not make this change, please contact us immediately at {settings.BUSINESS_EMAIL}

        --
        FilaOps
        """

        return self._send_email(user_email, subject, html_body, text_body)


# Singleton instance
email_service = EmailService()
