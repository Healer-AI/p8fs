"""Integration tests for the EmailService."""

from datetime import datetime

import pytest
from p8fs_cluster.config import config
from p8fs_cluster.logging import get_logger
from p8fs.services.email import EmailService

logger = get_logger(__name__)


@pytest.mark.integration
class TestEmailServiceIntegration:
    """Integration tests for EmailService with actual SMTP server."""

    def test_email_configuration_loaded(self):
        """Test that email configuration is properly loaded from environment."""
        assert config.email_username, "Email username should be configured"
        assert config.email_password, "Email password should be configured"
        assert config.email_smtp_server, "SMTP server should be configured"
        assert config.email_smtp_port, "SMTP port should be configured"
        
        logger.info(
            f"Email configuration loaded: user={config.email_username}, "
            f"server={config.email_smtp_server}:{config.email_smtp_port}"
        )

    def test_send_simple_email(self):
        """Test sending a simple email."""
        service = EmailService()
        
        # Send to the configured email address
        to_email = config.email_username
        subject = f"P8FS Core Email Integration Test - {datetime.now().isoformat()}"
        html_content = f"""
        <html>
        <body>
            <h2>P8FS Core Email Integration Test</h2>
            <p>This is a test email sent from the P8FS Core email service integration test.</p>
            <p>If you received this email, the email service is working correctly!</p>
            <ul>
                <li>Provider: {service.provider}</li>
                <li>SMTP Server: {service.smtp_server}</li>
                <li>Timestamp: {datetime.now().isoformat()}</li>
            </ul>
        </body>
        </html>
        """
        
        text_content = (
            f"P8FS Core Email Integration Test\n\n"
            f"This is a test email sent from the P8FS Core email service integration test.\n"
            f"Provider: {service.provider}\n"
            f"SMTP Server: {service.smtp_server}\n"
            f"Timestamp: {datetime.now().isoformat()}"
        )
        
        # Should not raise any exceptions
        service.send_email(
            subject=subject,
            html_content=html_content,
            to_addrs=to_email,
            text_content=text_content
        )
        
        logger.info(f"Successfully sent test email to {to_email}")

    def test_send_markdown_email(self):
        """Test sending an email from markdown content."""
        service = EmailService()
        
        to_email = config.email_username
        subject = f"P8FS Core Markdown Email Test - {datetime.now().isoformat()}"
        
        markdown_content = f"""
# P8FS Core Email Service Test

This email was generated from **Markdown** content!

## Features Tested

- Markdown to HTML conversion
- Table support
- Text formatting

## Test Results

| Feature | Status |
|---------|--------|
| Markdown Parsing | ✓ |
| HTML Generation | ✓ |
| Email Delivery | ✓ |

### Additional Information

- **Provider**: {service.provider}
- **Timestamp**: {datetime.now().isoformat()}
- **Environment**: {config.environment}

*This is an automated test email.*
        """
        
        service.send_digest_email_from_markdown(
            subject=subject,
            markdown_content=markdown_content,
            to_addrs=to_email
        )
        
        logger.info(f"Successfully sent markdown email to {to_email}")

    @pytest.mark.asyncio
    async def test_send_verification_code_async(self):
        """Test sending a verification code email asynchronously."""
        service = EmailService()
        
        to_email = config.email_username
        verification_code = "123456"
        
        # Should not raise any exceptions
        await service.send_verification_code(
            email=to_email,
            code=verification_code
        )
        
        logger.info(f"Successfully sent verification code to {to_email}")

    def test_send_multiple_recipients(self):
        """Test sending email to multiple recipients."""
        service = EmailService()
        
        # Use the same email address twice for testing
        recipients = [config.email_username, config.email_username]
        subject = f"P8FS Core Multi-Recipient Test - {datetime.now().isoformat()}"
        
        html_content = """
        <html>
        <body>
            <h2>Multi-Recipient Email Test</h2>
            <p>This email was sent to multiple recipients using the P8FS Core email service.</p>
        </body>
        </html>
        """
        
        service.send_email(
            subject=subject,
            html_content=html_content,
            to_addrs=recipients
        )
        
        logger.info(f"Successfully sent email to {len(recipients)} recipients")

    def test_mock_provider_skips_sending(self):
        """Test that mock provider doesn't actually send emails."""
        # Create service with mock provider
        service = EmailService(provider="mock")
        
        # This should not actually send an email
        service.send_email(
            subject="This should not be sent",
            html_content="<p>Mock email</p>",
            to_addrs="test@example.com"
        )
        
        # No exception should be raised, and no email should be sent
        logger.info("Mock provider correctly skipped email sending")

    @pytest.mark.asyncio
    async def test_verification_code_with_disabled_email(self):
        """Test verification code behavior when email is disabled."""
        # Create service that will check config.email_enabled
        service = EmailService()
        
        # If email is disabled in config, this should log but not send
        await service.send_verification_code(
            email="test@example.com",
            code="999999"
        )
        
        logger.info("Verification code handling completed")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])