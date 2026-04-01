"""Email sender module."""

from email.message import EmailMessage
import logging as log
import os
import smtplib


class EmailSender:
    """Handles sending emails using SMTP."""

    def __init__(self, *, armed: bool = False) -> None:
        """Initialize the EmailSender with SMTP configuration from environment variables."""

        # Secondary safety control to make sure we don't send emails while testing.
        self.armed = armed

        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.smtp_user = os.getenv("SMTP_USERNAME", "")
        self.smtp_pass = os.getenv("SMTP_PASSWORD", "")

        if not self.smtp_host or not self.smtp_from:
            log.error("SMTP_HOST and SMTP_FROM environment variables must be set.")
            raise ValueError("Missing required SMTP configuration.")

    def send(
        self,
        to_addr: str,
        subject: str,
        message: str,
        cc_addrs: list[str] | None = None,
    ) -> bool:
        """Send an email.

        Args:
            to_addr: The recipient's email address.
            subject: The subject of the email.
            message: The body of the email.
            cc_addrs: Optional CC recipients for the message.

        Returns:
            True if the email was sent successfully, False otherwise.
        """
        if not self.armed:
            return True

        cc_addrs = [addr.strip() for addr in (cc_addrs or []) if addr.strip()]

        email_message = EmailMessage()
        email_message["From"] = self.smtp_from
        email_message["To"] = to_addr
        if cc_addrs:
            email_message["Cc"] = ", ".join(cc_addrs)
        email_message["Subject"] = subject
        email_message.set_content(message)

        recipients = [to_addr, *cc_addrs]

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                if self.smtp_user and self.smtp_pass:
                    smtp.login(self.smtp_user, self.smtp_pass)
                smtp.sendmail(self.smtp_from, recipients, email_message.as_string())
            return True
        except Exception as e:
            log.error(e)
        return False


if __name__ == "__main__":
    pass
