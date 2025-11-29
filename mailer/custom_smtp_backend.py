from django.core.mail.backends.smtp import EmailBackend

class PatchedEmailBackend(EmailBackend):
    def open(self):
        if self.connection:
            return False

        connection_class = self.connection_class
        try:
            self.connection = connection_class(self.host, self.port, timeout=self.timeout)
            self.connection.ehlo()
            if self.use_tls:
                # ⛔ Patch: do NOT pass keyfile/certfile
                self.connection.starttls()
                self.connection.ehlo()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise
            return False
