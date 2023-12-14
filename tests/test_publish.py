import subprocess
from pathlib import Path

from packse import __development_base_path__

from .common import snapshot_command, tmpchdir
import tempfile
import shutil
import packse.publish
import pytest
import stat
import re
import subprocess
from typing import Generator
from unittest.mock import MagicMock


@pytest.fixture(scope="module")
def scenario_dist() -> Generator[Path, None, None]:
    target = __development_base_path__ / "scenarios" / "example.json"

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.check_call(
            ["packse", "build", str(target)],
            cwd=tmpdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        dists = list((Path(tmpdir) / "dist").iterdir())
        assert len(dists) == 1
        dist = dists[0]

        yield dist


class MockBinary:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.callback = None
        self._update_bin("")

    def _prepare_text(self, text: str = None):
        if not text:
            return ""
        # Escape single quotes
        return text.replace("'", "\\'")

    def _update_bin(self, content: str):
        self.path.write_text("#!/usr/bin/env sh\n\n" + content + "\n")
        self.path.chmod(self.path.stat().st_mode | stat.S_IEXEC)

    def set_success(self, text: str | None = None):
        text = self._prepare_text(text)
        self._update_bin(f"echo '{text}'")

    def set_error(self, text: str | None = None):
        text = self._prepare_text(text)
        self._update_bin(f"echo '{text}'; exit 1")


@pytest.fixture
def mock_twine(monkeypatch: pytest.MonkeyPatch) -> Generator[MockBinary, None, None]:
    # Create a temp directory to register as a bin
    with tempfile.TemporaryDirectory() as tmpdir:
        mock = MockBinary(Path(tmpdir) / "twine")
        mock.set_success()

        # Add to the path
        monkeypatch.setenv("PATH", tmpdir, prepend=":")
        assert shutil.which("twine").startswith(tmpdir)

        yield mock


def test_publish_example_dry_run(snapshot, scenario_dist: Path):
    assert (
        snapshot_command(
            ["publish", "--dry-run", scenario_dist],
            extra_filters=[(re.escape(str(scenario_dist)), "[DISTDIR]")],
        )
        == snapshot
    )


def test_publish_example_twine_succeeds(
    snapshot, scenario_dist: Path, mock_twine: MockBinary
):
    mock_twine.set_success("<twine happy message>")

    assert (
        snapshot_command(
            ["publish", scenario_dist, "-v"],
            extra_filters=[(re.escape(str(scenario_dist)), "[DISTDIR]")],
        )
        == snapshot
    )


def test_publish_example_twine_fails_with_unknown_error(
    snapshot, scenario_dist: Path, mock_twine: MockBinary
):
    mock_twine.set_error("<twine error message>")

    assert (
        snapshot_command(
            ["publish", scenario_dist, "-v"],
            extra_filters=[(re.escape(str(scenario_dist)), "[DISTDIR]")],
        )
        == snapshot
    )


def test_publish_example_twine_fails_with_rate_limit(
    snapshot, scenario_dist: Path, mock_twine: MockBinary
):
    mock_twine.set_error(
        """
Uploading distributions to https://test.pypi.org/legacy/
Uploading 
requires_transitive_incompatible_with_root_version_5c1b7dc1_c-1.0.0-py3-none-any
.whl
25l
    0% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/4.1 kB • --:-- • ?
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.1/4.1 kB • 00:00 • ?
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.1/4.1 kB • 00:00 • ?
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.1/4.1 kB • 00:00 • ?
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.1/4.1 kB • 00:00 • ?
25hWARNING  Error during upload. Retry with the --verbose option for more details. 
ERROR    HTTPError: 429 Too Many Requests from https://test.pypi.org/legacy/    
            Too many new projects created   
        """
    )

    assert (
        snapshot_command(
            ["publish", scenario_dist, "-v"],
            extra_filters=[(re.escape(str(scenario_dist)), "[DISTDIR]")],
        )
        == snapshot
    )


def test_publish_example_twine_fails_with_already_exists(
    snapshot, scenario_dist: Path, mock_twine: MockBinary
):
    mock_twine.set_error(
        """
Uploading distributions to https://test.pypi.org/legacy/
Uploading example_9e723676_a-1.0.0.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.1/3.1 kB • 00:00 • ?
WARNING  Error during upload. Retry with the --verbose option for more details.                                              
ERROR    HTTPError: 400 Bad Request from https://test.pypi.org/legacy/                                                       
         File already exists. See https://test.pypi.org/help/#file-name-reuse for more information.  
        """
    )

    assert (
        snapshot_command(
            ["publish", scenario_dist, "-v"],
            extra_filters=[(re.escape(str(scenario_dist)), "[DISTDIR]")],
        )
        == snapshot
    )
