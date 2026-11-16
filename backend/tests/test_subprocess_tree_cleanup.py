import pytest
import asyncio
import os
import signal
import sys
from backend.app.services.kane_service import terminate_process_tree
from backend.app.services.runner_service import runner_service

@pytest.mark.asyncio
async def test_subprocess_tree_cleanup_terminates_descendants(tmp_path):
    """
    Spawns a multi-process hierarchy (parent -> child -> grandchild)
    with start_new_session=True, then calls terminate_process_tree.
    Verifies that all child and grandchild processes are cleanly killed.
    """
    pid_log = tmp_path / "pids.log"
    grandchild_file = tmp_path / "grandchild.py"
    child_file = tmp_path / "child.py"
    parent_file = tmp_path / "parent.py"

    grandchild_file.write_text(f"""
import time, os, sys
with open(sys.argv[1], "a") as f:
    f.write(f"grandchild:{{os.getpid()}}\\n")
while True:
    time.sleep(0.5)
""")

    child_file.write_text(f"""
import subprocess, time, os, sys
with open(sys.argv[1], "a") as f:
    f.write(f"child:{{os.getpid()}}\\n")
p = subprocess.Popen([sys.executable, "{str(grandchild_file)}", sys.argv[1]])
while True:
    time.sleep(0.5)
""")

    parent_file.write_text(f"""
import subprocess, time, os, sys
with open(sys.argv[1], "a") as f:
    f.write(f"parent:{{os.getpid()}}\\n")
p = subprocess.Popen([sys.executable, "{str(child_file)}", sys.argv[1]])
while True:
    time.sleep(0.5)
""")

    # Spawn parent with start_new_session=True
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(parent_file),
        str(pid_log),
        start_new_session=True
    )

    # Wait for pids.log to have all 3 PIDs
    pids = {}
    for _ in range(30):
        await asyncio.sleep(0.2)
        if pid_log.exists():
            lines = pid_log.read_text().strip().splitlines()
            for line in lines:
                if ":" in line:
                    role, pid_str = line.split(":")
                    pids[role] = int(pid_str)
            if len(pids) >= 3:
                break

    assert "parent" in pids
    assert "child" in pids
    assert "grandchild" in pids

    # Verify all 3 are running
    for role, pid in pids.items():
        try:
            os.kill(pid, 0)
        except OSError:
            pytest.fail(f"Process {role} (PID {pid}) died prematurely before test")

    # Now terminate entire tree
    await terminate_process_tree(proc, timeout_sec=1.5)

    # Verify all 3 processes are dead
    await asyncio.sleep(0.5)
    for role, pid in pids.items():
        is_alive = True
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            is_alive = False
        assert not is_alive, f"Process {role} (PID {pid}) survived terminate_process_tree!"

@pytest.mark.asyncio
async def test_runner_service_terminate_all_processes():
    """
    Verifies that runner_service.terminate_all_processes terminates all tracked active processes.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)",
        start_new_session=True
    )
    pid = proc.pid
    runner_service._active_processes["test_run_tree"] = proc

    # Verify running
    os.kill(pid, 0)

    # Call terminate_all_processes
    await runner_service.terminate_all_processes()

    assert "test_run_tree" not in runner_service._active_processes
    await asyncio.sleep(0.3)

    # Verify dead
    with pytest.raises(OSError):
        os.kill(pid, 0)
