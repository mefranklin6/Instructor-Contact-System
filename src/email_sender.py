import os
import smtplib
import logging as log


class EmailSender:
    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_from = os.getenv("SMTP_FROM", "")
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")

        if not self.smtp_host or not self.smtp_from:
            log.error("SMTP_HOST and SMTP_FROM environment variables must be set.")
            raise ValueError("Missing required SMTP configuration.")

    def send(self, to_addr, subject, message) -> bool:
        message = f"""From: {self.smtp_from}
To: {to_addr}
Subject: {subject}

{message}"""

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                if self.smtp_user and self.smtp_pass:
                    smtp.login(self.smtp_user, self.smtp_pass)
                smtp.sendmail(self.smtp_from, to_addr, message)
            return True
        except Exception as e:
            log.error(e)
        return False


if __name__ == "__main__":
    pass
