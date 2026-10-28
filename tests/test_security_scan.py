from pathlib import Path
from scripts.security_scan import scan


def test_scanner_reports_type_without_exposing_value(tmp_path: Path):
    text='AKIA'+'A'*16
    (tmp_path/'service.py').write_text(f'key="{text}"\n')
    assert scan(tmp_path)==[('service.py',1,'aws_access_key_id')]


def test_scanner_excludes_test_fixture_and_template(tmp_path: Path):
    (tmp_path/'tests').mkdir()
    (tmp_path/'tests'/'example.py').write_text('-----BEGIN PRIVATE KEY-----')
    (tmp_path/'.env.example').write_text('-----BEGIN PRIVATE KEY-----')
    assert scan(tmp_path)==[]
