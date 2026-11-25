"""Disposable PTY primitives for both shell and Configurator tests."""

import fcntl
import os
import pty
import select
import struct
import subprocess
import termios


def open_terminal(rows=40, columns=110):
    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        return master, slave, termios.tcgetattr(slave)
    except BaseException:
        os.close(master)
        os.close(slave)
        raise


def run_with_terminal_stdout(command, *, cwd, env):
    """Run a short command with TTY stdout and separately captured stderr."""
    master, slave = pty.openpty()
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, stdout=slave, stderr=subprocess.PIPE, text=True, timeout=5
        )
        ready, _, _ = select.select([master], [], [], 1)
        output = os.read(master, 4096).decode() if ready else ""
        return result, output
    finally:
        os.close(slave)
        os.close(master)
