from unittest.mock import patch, MagicMock
from app_factory.executors.subprocess_transport import SubprocessTransport, SubprocessResult, build_claude_code_command, build_codex_command

def test_build_claude_code_command():
    cmd = build_claude_code_command(prompt="implement auth", working_dir="/tmp/project")
    assert "claude" in cmd[0]
    assert any("--print" in c for c in cmd)

def test_build_codex_command():
    cmd = build_codex_command(prompt="implement auth", working_dir="/tmp/project")
    assert "codex" in cmd[0]

def test_subprocess_transport_submit():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.poll.return_value = None
    with patch("subprocess.Popen", return_value=mock_process):
        receipt = transport.submit(command=["echo", "test"], working_dir="/tmp", timeout=60)
    assert receipt.status == "running"

def test_subprocess_transport_poll_completed():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.communicate.return_value = ("output text", "")
    transport._processes["exec-1"] = mock_process
    result = transport.poll("exec-1")
    assert result.status == "completed"
    assert result.stdout == "output text"

def test_subprocess_transport_poll_running():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    transport._processes["exec-1"] = mock_process
    result = transport.poll("exec-1")
    assert result.status == "running"

def test_subprocess_transport_poll_failed():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = 1
    mock_process.communicate.return_value = ("", "error occurred")
    transport._processes["exec-1"] = mock_process
    result = transport.poll("exec-1")
    assert result.status == "failed"
    assert "error" in result.stderr

def test_subprocess_transport_cancel():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    transport._processes["exec-1"] = mock_process
    result = transport.cancel("exec-1")
    mock_process.terminate.assert_called_once()
    assert result.status == "cancelled"

def test_subprocess_transport_timeout():
    transport = SubprocessTransport()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    transport._processes["exec-1"] = mock_process
    transport._timeouts["exec-1"] = 0
    transport._start_times["exec-1"] = 0
    result = transport.poll("exec-1", check_timeout=True)
    assert result.status == "timed_out"
