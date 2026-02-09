import os
import smtplib
import logging as log


class EmailSender:

    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.csuchico.edu")
        self.smtp_port = 587
        self.smtp_from = os.getenv("SMTP_FROM", "classroom@csuchico.edu")
        self.smtp_user = None
        self.smtp_pass = None
        # TODO: add credentials and remove defaults

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
    test = EmailSender()
    test.send("mefranklin@csuchico.edu", "Test EmailSender", "hello\rworld")
