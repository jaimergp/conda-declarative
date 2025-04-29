""" """

from conda.exceptions import CondaExitZero


class LockOnlyExit(CondaExitZero):
    def __init__(self):
        msg = "Lock-only run. Exiting."
        super().__init__(msg)
