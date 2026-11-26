import ctypes
import time


class WindowsClock:
    def __init__(self):
        self.awake = ctypes.windll.kernel32.QueryUnbiasedInterruptTime
        self.awake.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        self.uptime = ctypes.windll.kernel32.GetTickCount64
        self.uptime.restype = ctypes.c_ulonglong
        self.sleep_offset = None

    def sample(self):
        ticks = ctypes.c_ulonglong()
        if not self.awake(ctypes.byref(ticks)):
            raise ctypes.WinError()
        active = ticks.value // 10000
        offset = self.uptime() - active
        woke = self.sleep_offset is not None and offset - self.sleep_offset > 1000
        self.sleep_offset = offset
        return active, time.time_ns() // 1_000_000, woke
