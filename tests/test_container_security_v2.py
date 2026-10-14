"""Container Security Profile v2 tests (G1).

Mirrors the exact flag set used by ContainerHarnessRunner.run_task
(src/causalevo/eval/harness_agent.py). Cheap probes use python:3.11-slim;
the provider-allowlist test uses the real tape-server container.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from causalevo.eval.executor import docker_available
from causalevo.eval.networks import ProviderContainer, ensure_internal_network

pytestmark = pytest.mark.skipif(not docker_available(), reason="docker unavailable")

NETWORK = "ceval-net"


def _flags(workdir: Path) -> list[str]:
    """The v2 security flag set, kept in sync with ContainerHarnessRunner."""
    return [
        "--network", NETWORK,
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--tmpfs", "/home/agent/.cache:rw,exec,nosuid,size=64m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", "768m", "--memory-swap", "768m",
        "--cpus", "1", "--pids-limit", "128",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{workdir.resolve()}:/work",
        "-w", "/work",
    ]


def _probe(code: str, workdir: Path, image: str = "python:3.11-slim") -> subprocess.CompletedProcess:
    cmd = ["docker", "run", "--rm", "--name", f"ceval-sec-{uuid.uuid4().hex[:10]}",
           *_flags(workdir), image, "python", "-c", code]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("secv2-ws")
    (d / "solution.py").write_text("# task\n", encoding="utf-8")
    return d


def test_rootfs_is_read_only(workdir):
    proc = _probe(
        "import sys\n"
        "try:\n    open('/usr/bin/evil','w'); print('WROTE_ROOTFS')\n"
        "except OSError: print('RO_OK')\n"
        "try:\n    open('/etc/hostname','a'); print('WROTE_ETC')\n"
        "except OSError: print('ETC_OK')",
        workdir)
    assert "RO_OK" in proc.stdout and "ETC_OK" in proc.stdout
    assert "WROTE" not in proc.stdout


def test_tmp_is_writable(workdir):
    proc = _probe("open('/tmp/scratch.txt','w').write('x'); print('TMP_OK')", workdir)
    assert "TMP_OK" in proc.stdout


def test_workspace_is_writable_and_visible_on_host(workdir):
    marker = f"agent-wrote-{uuid.uuid4().hex[:8]}.txt"
    proc = _probe(f"open('/work/{marker}','w').write('hi'); print('WS_OK')", workdir)
    assert "WS_OK" in proc.stdout
    assert (workdir / marker).read_text() == "hi"


def test_no_new_privileges(workdir):
    proc = _probe(
        "print([l for l in open('/proc/self/status') if l.startswith('NoNewPrivs')][0])",
        workdir)
    assert "NoNewPrivs:\t1" in proc.stdout


def test_all_capabilities_dropped(workdir):
    proc = _probe(
        "print([l for l in open('/proc/self/status') if l.startswith('CapEff')][0])",
        workdir)
    assert "CapEff:\t0000000000000000" in proc.stdout


def test_internal_network_denies_internet_and_metadata(workdir):
    ensure_internal_network(NETWORK)
    proc = _probe(
        "import socket\n"
        "def probe(host, port):\n"
        "    try:\n        socket.create_connection((host, port), timeout=3).close(); print('OPEN', host)\n"
        "    except Exception as e: print('DENIED', host, type(e).__name__)\n"
        "probe('1.1.1.1', 443)\n"
        "probe('169.254.169.254', 80)\n"
        "try:\n    print('DNS', socket.gethostbyname('api.deepseek.com'))\n"
        "except Exception as e: print('DNS_DENIED', type(e).__name__)",
        workdir)
    assert "OPEN" not in proc.stdout
    assert proc.stdout.count("DENIED") >= 2
    assert "DNS " not in proc.stdout  # no resolution printed


def test_provider_endpoint_reachable_on_internal_network(workdir):
    """The allowlist positive control: the ONLY reachable service is the
    provider on the internal network."""
    ensure_internal_network(NETWORK)
    tape = {"0": [["text", "allowlist-ok"]]}
    with ProviderContainer(tape, network=NETWORK) as provider:
        proc = _probe(
            "import urllib.request, json\n"
            f"req = urllib.request.Request('{provider.endpoint}/chat/completions', "
            "data=b'{\"messages\": []}', headers={'Content-Type': 'application/json'})\n"
            "body = urllib.request.urlopen(req, timeout=10).read().decode()\n"
            "print('SSE_OK' if 'allowlist-ok' in body else 'BAD_BODY')",
            workdir)
        assert "SSE_OK" in proc.stdout


def test_host_filesystem_not_visible(workdir, tmp_path):
    canary = tmp_path / f"canary-{uuid.uuid4().hex[:6]}.txt"
    secret = f"CANARY_{uuid.uuid4().hex}"
    canary.write_text(secret, encoding="utf-8")
    proc = _probe(
        "import os\n"
        f"p = r'{canary}'\n"
        "print('HOST_PATH_LEAK' if os.path.exists(p) else 'HOST_PATH_ABSENT')\n"
        "print('ROOT_DIRS', sorted(os.listdir('/')))",
        workdir)
    assert "HOST_PATH_ABSENT" in proc.stdout
    assert secret not in proc.stdout
    assert "Users" not in proc.stdout  # no Windows host dirs


def test_symlink_escape_fails(workdir, tmp_path):
    canary = tmp_path / "secret-target.txt"
    secret = f"CANARY_{uuid.uuid4().hex}"
    canary.write_text(secret, encoding="utf-8")
    # create the symlink inside the container (host Windows symlink perms vary)
    proc = _probe(
        "import os\n"
        f"os.symlink(r'{canary}', '/work/escape_link')\n"
        "try:\n    print(open('/work/escape_link').read())\n"
        "except Exception as e: print('ESCAPE_BLOCKED', type(e).__name__)",
        workdir)
    assert "ESCAPE_BLOCKED" in proc.stdout
    assert secret not in proc.stdout
