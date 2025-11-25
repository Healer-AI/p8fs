"""Test configuration for JWT manager tests."""

from unittest.mock import Mock

# Create a mock config object with all required attributes
mock_config = Mock()
mock_config.auth_jwt_rotation_days = 30
mock_config.auth_jwt_issuer = "test-issuer"
mock_config.auth_jwt_audience = "test-audience"
mock_config.auth_access_token_ttl = 3600
mock_config.auth_refresh_token_ttl = 86400
mock_config.auth_device_code_ttl = 600
mock_config.auth_code_ttl = 600
mock_config.auth_challenge_ttl = 300
mock_config.auth_max_devices_per_email = 5
mock_config.auth_max_devices_per_user = 10
mock_config.auth_master_derivation_key = None
mock_config.auth_s3_credential_ttl = 3600
mock_config.auth_api_key_ttl = 86400
mock_config.auth_rsa_key_size = 2048
mock_config.auth_aes_key_size = 256
mock_config.auth_pbkdf2_iterations = 100000
mock_config.auth_base_url = "https://auth.p8fs.com"
mock_config.auth_qr_code_size = 400
mock_config.storage_s3_region = "us-east-1"
mock_config.storage_s3_endpoint_url = "http://localhost:9000"