from packages.redaction import redact_sensitive


def test_prompt_redacts_common_credentials_without_rewriting_repository():
    original = '''api_key = "sk-abcdefghijklmnopqrstuvwx"
password='super-sensitive-value'
access_token: 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'
key = "AKIAABCDEFGHIJKLMNOP"
-----BEGIN PRIVATE KEY-----
aaaaaaa
-----END PRIVATE KEY-----
'''
    cleaned = redact_sensitive(original)
    assert 'super-sensitive-value' not in cleaned
    assert 'ghp_abcdefghijklmnopqrstuvwxyz0123456789' not in cleaned
    assert 'AKIAABCDEFGHIJKLMNOP' not in cleaned
    assert 'BEGIN PRIVATE KEY' not in cleaned
    assert 'sk-abcdefghijklmnopqrstuvwx' not in cleaned
    assert '[REDACTED]' in cleaned
    assert original.startswith('api_key')
