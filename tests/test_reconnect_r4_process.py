import base64
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys
import time
import unittest

from sandbox.reconnect_r4_process import BoundedProcess, complete

CHILD = str(Path(__file__).with_name("reconnect_r4_process_child.py"))


@unittest.skipUnless(os.name == "nt", "Windows job adapter")
class ProcessTests(unittest.TestCase):
    def run_child(self, mode, timeout=2, cap=1048576, **kwargs):
        argv = [sys.executable, "-I", "-S", CHILD, mode]
        row = BoundedProcess([argv], **kwargs).run(argv, sequence=1, timeout_seconds=timeout, max_output_bytes=cap)
        for stream in ("stdout", "stderr"):
            raw = base64.b64decode(row[stream + "_base64"], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row[stream + "_sha256"])
        self.assertLessEqual(row["retained_output_bytes"], cap)
        return row

    def test_separate_streams_and_owned_job(self):
        row = self.run_child("streams")
        self.assertTrue(complete(row), row)
        self.assertEqual((row["stdout"], row["stderr"], row["returncode"]), ("stdout\n", "stderr\n", 0))

    def test_byte_flood_stops_with_bounded_combined_memory(self):
        row = self.run_child("flood", cap=32768)
        self.assertTrue(row["truncated"] and row["reader_threads_joined"] and row["process_reaped"])
        self.assertFalse(complete(row))

    def test_timeout_retains_partial_output_and_reaps(self):
        row = self.run_child("sleep", timeout=0.5)
        self.assertTrue(row["timed_out"] and row["reader_threads_joined"] and row["process_reaped"])
        self.assertIn("partial-before-timeout", row["stdout"])
        self.assertLess((row["monotonic_end_ns"] - row["monotonic_start_ns"]) / 1e9, 2.5)

    def test_descendant_holding_pipe_cannot_outlive_owned_job(self):
        row = self.run_child("descendant", timeout=0.5)
        self.assertTrue(row["timed_out"] and row["reader_threads_joined"])
        pid = int(row["stdout"].splitlines()[0])
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                status = wintypes.DWORD()
                self.assertTrue(api.GetExitCodeProcess(handle, ctypes.byref(status)))
                self.assertNotEqual(status.value, 259)  # STILL_ACTIVE
            finally:
                api.CloseHandle(handle)

    def test_job_assignment_failure_never_sends_go(self):
        def fail(_):
            raise OSError("fixture job assignment denied")
        row = self.run_child("streams", job_factory=fail)
        self.assertFalse(row["launcher_go_sent"])
        self.assertTrue(row["process_reaped"])
        self.assertEqual(row["stdout"], "")
        self.assertIn("assignment denied", row["capture_error"])

    def test_invalid_utf8_preserves_raw_bytes_not_relabelled_success(self):
        row = self.run_child("invalid-utf8")
        self.assertFalse(complete(row))
        self.assertEqual(base64.b64decode(row["stdout_base64"]), b"valid\xffpartial")

    def test_nonzero_exit_is_retained_for_caller_acceptance(self):
        row = self.run_child("exit-failure")
        self.assertTrue(complete(row))
        self.assertEqual(row["returncode"], 7)

    def test_no_command_outside_allowlist_or_bounds(self):
        adapter = BoundedProcess([])
        with self.assertRaises(PermissionError):
            adapter.run(["docker", "ps"], sequence=1)


if __name__ == "__main__":
    unittest.main()
