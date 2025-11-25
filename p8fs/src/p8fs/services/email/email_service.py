"""
EmailService: a simple SMTP-based email sending service.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from p8fs_cluster.config import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """
    Email service for sending HTML emails via SMTP.
    Defaults to Gmail SMTP using the configured service account email.
    """

    def __init__(
        self,
        provider: str = None,
        smtp_server: str = None,
        smtp_port: int = None,
        use_tls: bool = None,
        username: str = None,
        password: str = None,
        sender_name: str = None,
    ):
        self.provider = provider or config.email_provider
        self.smtp_server = smtp_server or config.email_smtp_server
        self.smtp_port = smtp_port or config.email_smtp_port
        self.use_tls = use_tls if use_tls is not None else config.email_use_tls
        self.username = username or config.email_username
        self.password = password or config.email_password
        self.sender = sender_name or config.email_sender_name

        # Log configuration (without password)
        logger.info(
            f"EmailService initialized: provider={self.provider}, server={self.smtp_server}:{self.smtp_port}, username={self.username}, tls={self.use_tls}"
        )
        if not self.password:
            logger.warning("EMAIL_PASSWORD is not set - email sending will fail")

    async def send_verification_code(self, email: str, code: str) -> None:
        """Send verification code to email."""
        # Check if email is disabled or not configured properly
        if not config.email_enabled or not self.password or self.provider == "mock":
            logger.info(f"📧 EMAIL SKIPPED: Verification code for {email}: {code}")
            if not config.email_enabled:
                logger.info(
                    "   Reason: Email sending disabled (P8FS_EMAIL_ENABLED=false)"
                )
            elif not self.password:
                logger.info("   Reason: No email password configured")
            elif self.provider == "mock":
                logger.info("   Reason: Mock email provider")
            return

        subject = "EEPIS Verification Code"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #333; text-align: center;">EEPIS Authentication</h2>
                <p style="color: #666; font-size: 16px;">Your verification code is:</p>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; text-align: center; margin: 20px 0;">
                    <h1 style="color: #007bff; letter-spacing: 5px; font-size: 36px; margin: 0;">{code}</h1>
                </div>
                <p style="color: #666; font-size: 14px;">This code will expire in 10 minutes.</p>
                <p style="color: #999; font-size: 12px; margin-top: 30px; text-align: center;">If you didn't request this code, please ignore this email.</p>
            </div>
        </body>
        </html>
        """

        text_content = f"Your EEPIS verification code is: {code}\n\nThis code will expire in 10 minutes."

        # Use sync method wrapped in async
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self.send_email, subject, html_content, email, text_content
        )

    def send_digest_email_from_markdown(
        self,
        subject: str,
        markdown_content: str,
        to_addrs: str | list[str],
        from_addr: str | None = None,
    ):
        """
        given markdown send a html email
        """
        import markdown

        html = markdown.markdown(markdown_content, extensions=["tables"])

        return self.send_email(
            subject=subject, html_content=html, to_addrs=to_addrs, from_addr=from_addr
        )

    def send_email(
        self,
        subject: str,
        html_content: str,
        to_addrs: str | list[str],
        text_content: str | None = None,
        from_addr: str | None = None,
    ) -> None:
        """
        Send an email with both plain text and HTML content.

        :param subject: Subject of the email.
        :param html_content: HTML body of the email.
        :param to_addrs: Recipient email address or list of addresses.
        :param text_content: Optional plain text body. If not provided, only HTML will be sent.
        :param from_addr: Email address of the sender. Defaults to configured username.


        For the Gmail provider for example enable 2FA on your account and add
        App Passwords for the account and use email:app_password to authenticate

        """
        # Skip sending email if provider is mock
        if self.provider == "mock":
            logger.info(f"Mock email: To={to_addrs}, Subject={subject}")
            return

        if from_addr is None:
            from_addr = self.username
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        # Create multipart message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = (
            formataddr((self.sender, from_addr)) if self.sender else from_addr
        )
        message["To"] = ", ".join(to_addrs)

        # Attach plain text part if provided
        if text_content:
            part1 = MIMEText(text_content, "plain")
            message.attach(part1)

        # Attach HTML part
        part2 = MIMEText(html_content, "html")
        message.attach(part2)

        # Send via SMTP
        try:
            if self.use_tls:
                logger.debug(
                    f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port} with TLS"
                )
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                try:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    logger.debug(f"Attempting login with username: {self.username}")
                    server.login(self.username, self.password)
                    server.sendmail(from_addr, to_addrs, message.as_string())
                    logger.info(f"Email sent successfully to {', '.join(to_addrs)}")
                finally:
                    server.quit()
            else:
                logger.debug(
                    f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port} with SSL"
                )
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
                try:
                    logger.debug(f"Attempting login with username: {self.username}")
                    server.login(self.username, self.password)
                    server.sendmail(from_addr, to_addrs, message.as_string())
                    logger.info(f"Email sent successfully to {', '.join(to_addrs)}")
                finally:
                    server.quit()
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed for {self.username}: {e}")
            logger.error(
                "Please check EMAIL_USERNAME and EMAIL_PASSWORD environment variables"
            )
            logger.error(
                "For Gmail, ensure you're using an app-specific password, not your regular password"
            )
            raise
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error occurred: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise