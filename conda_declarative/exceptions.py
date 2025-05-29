from conda.exceptions import CondaExitZero


class LockOnlyExit(CondaExitZero):
    """Exception raised to prevent linking from happening during `execute_apply`."""

    def __init__(self):
        msg = "Lock-only run. Exiting."
        super().__init__(msg)
