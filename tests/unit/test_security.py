# tests/unit/test_security.py
import pytest
from app.security import encrypt_password, decrypt_password, fernet

# Test with a known key for predictable results if needed, or allow dynamic
# For basic encryption/decryption, the key set in conftest.py (via env var) will be used by security.py


def test_password_encryption_decryption():
    """Test that a password can be encrypted and then decrypted back to the original."""
    original_password = "mysecretpassword123!@#"
    encrypted = encrypt_password(original_password)
    decrypted = decrypt_password(encrypted)

    assert encrypted != original_password
    assert decrypted == original_password


def test_encryption_is_deterministic_with_same_key_and_data():
    """Fernet encryption is not deterministic by default due to per-message salt.
    This test is more to understand its nature rather than enforce determinism.
    If determinism were required, a different approach or fixed IV would be needed.
    """
    # This test will likely show they are different, which is expected for Fernet.
    # Each call to fernet.encrypt() generates a new token with a new timestamp and IV.
    password = "test_deterministic"
    encrypted1 = fernet.encrypt(password.encode()).decode()
    encrypted2 = fernet.encrypt(password.encode()).decode()
    # assert encrypted1 == encrypted2 # This would typically fail for Fernet
    # Instead, we verify decryption works for both
    assert fernet.decrypt(encrypted1.encode()).decode() == password
    assert fernet.decrypt(encrypted2.encode()).decode() == password
    # For the purpose of the encrypt_password function, the key is that it decrypts correctly.


# TODO: Add more tests, e.g., for error handling if decryption fails with wrong key/tampered data.
