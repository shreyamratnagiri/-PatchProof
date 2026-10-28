import pytest
from packages.git_import import github_url

@pytest.mark.parametrize('invalid',[
 'http://github.com/a/b','https://127.0.0.1/a/b','https://github.com@127.0.0.1/a/b',
 'https://github.com/a/b#frag','https://github.com/a/b?token=abc','file:///etc/passwd',
 'https://github.com/a/b/c','https://github.com/a/b:22',
])
def test_reject_unsafe_git_location(invalid):
    with pytest.raises(ValueError):github_url(invalid)

def test_canonical_github_location():
    assert github_url('https://github.com/example/repository')=='https://github.com/example/repository.git'
