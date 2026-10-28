"""Regression gates against destructive migration targeting in local scripts."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_bash_verifier_forces_disposable_database_before_migrations():
    source=(ROOT/'scripts/verify.sh').read_text()
    assert 'mktemp -d' in source
    assert 'export PATCHPROOF_DATABASE_URL="sqlite:///$verification_root/verification.db"' in source
    assert source.index('export PATCHPROOF_DATABASE_URL="sqlite:///$verification_root/verification.db"') < source.index('run "migration"')
    assert 'trap cleanup_verification EXIT' in source


def test_powershell_verifier_forces_disposable_database_before_migrations():
    source=(ROOT/'scripts/verify.ps1').read_text()
    assert '[guid]::NewGuid()' in source
    assert '$env:PATCHPROOF_DATABASE_URL = "sqlite:///$sqlitePath"' in source
    assert source.index('$env:PATCHPROOF_DATABASE_URL = "sqlite:///$sqlitePath"') < source.index("Invoke-Check 'migration'")
    assert 'Remove-Item -LiteralPath $verificationRoot' in source


def test_model_repair_demos_use_isolated_storage():
    bash=(ROOT/'scripts/run_repair_demo.sh').read_text()
    powershell=(ROOT/'scripts/run_repair_demo.ps1').read_text()
    assert 'mktemp -d' in bash
    assert bash.index('export PATCHPROOF_DATABASE_URL="sqlite:///$demo_root/demo.db"') < bash.index('scripts.repair_smoke')
    assert '[guid]::NewGuid()' in powershell
    assert powershell.index('$env:PATCHPROOF_DATABASE_URL = "sqlite:///$sqlitePath"') < powershell.index('scripts.repair_smoke')
