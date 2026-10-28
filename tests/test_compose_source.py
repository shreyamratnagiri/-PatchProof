"""Source contract only: actual Compose deployment still needs Docker verification."""
from pathlib import Path
import yaml


def test_api_never_receives_docker_socket_and_depends_on_migration():
    compose = yaml.safe_load(Path('docker-compose.yml').read_text())
    api = compose['services']['api']
    assert api['depends_on']['migrate']['condition'] == 'service_completed_successfully'
    assert api['depends_on']['prepare-data']['condition'] == 'service_completed_successfully'
    assert 'docker.sock' not in str(api)
    assert api['read_only'] is True
    assert 'no-new-privileges:true' in api['security_opt']
    assert '0:0' != str(api['user'])
    assert compose['services']['prepare-data']['restart'] == 'no'
    assert 'chown' in ' '.join(compose['services']['prepare-data']['command'])
