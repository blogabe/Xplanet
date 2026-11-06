"""Fixed-size disposable PTYs; callers retain child ownership and assertions."""
import fcntl
import os
import pty
import struct
import termios


def open_terminal(rows=40, columns=110):
    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ,
                    struct.pack('HHHH', rows, columns, 0, 0))
        return master, slave, termios.tcgetattr(slave)
    except BaseException:
        os.close(master)
        os.close(slave)
        raise
