"""Browser fixtures must be committed; browser integration cannot fetch external artifacts."""
from pathlib import Path
import io
import zipfile
from packages.ingest import extract_archive
from packages.verification import _choose_python_framework

ROOT = Path(__file__).resolve().parents[1]


def test_playwright_repair_fixture_is_complete(tmp_path: Path):
    fixture = ROOT / 'apps/web/e2e/fixtures/calculator.zip'
    assert fixture.is_file(), 'Playwright requires the committed repository ZIP fixture'
    assert fixture.stat().st_size < 100_000
    extract_archive(fixture.read_bytes(), tmp_path/'repo')
    source = (tmp_path/'repo/calculator.py').read_text()
    assert 'return a-b' in source
    assert _choose_python_framework(tmp_path/'repo', 'auto') == 'unittest'


def test_browser_launch_never_reuses_undocumented_local_server():
    config = (ROOT/'apps/web/playwright.config.ts').read_text()
    assert config.count('reuseExistingServer: false') == 2
    assert 'PATCHPROOF_DATABASE_URL: sqliteUrl' in config
