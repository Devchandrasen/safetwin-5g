"""R5 incremental clock journal. No process, network or power API.

This is a separately testable integration component, not an execution runner.
The caller owns authorization, command containment and the full rollback plan.
"""
import copy
import json
import os
from pathlib import Path

from sandbox.reconnect_r5_clock import (
    MAX_POINTS, NS, POINT_KEYS, EPOCH_TICKS, MAX_BRACKET_NS, TOLERANCE_NS,
    UTC_READ_ALLOWANCE_NS, integer, require, validate_descriptor,
)

CONTRACT_ID = "safetwin5g-reconnect-r5-journal-v1"
RESERVED_CLEANUP_POINTS = 256
ADMISSION_POINT_LIMIT = MAX_POINTS - RESERVED_CLEANUP_POINTS


class Prefix:
    """Incremental equivalent of the frozen all-pair predicate, O(n squared).

    Never evict an earlier point or clear a rejection. The frozen independent
    rational auditor, not this class, checks released traces.
    """
    def __init__(self, descriptor):
        validate_descriptor(descriptor)
        self.descriptor = copy.deepcopy(descriptor)
        self.points = []
        self.report = dict(clock_capture_valid=False, accepted_points=0, comparisons=0,
                           max_bracket_ns_ceil=0, max_abs_residual_ns_ceil=0, rejection=None)

    def add(self, point):
        if len(self.points) >= MAX_POINTS:
            raise ValueError("point capacity exhausted")
        row = copy.deepcopy(point)
        self.points.append(row)
        if self.report["rejection"] is not None:
            return self.status()
        index, against = len(self.points), None
        r, f = self.report, self.descriptor["frequency_hz"]
        try:
            require(type(row) is dict and set(row) == POINT_KEYS, "point-schema")
            require(integer(row["sequence"], 1, MAX_POINTS) and row["sequence"] == index
                    and row["clock_id"] == self.descriptor["clock_id"], "point-order-or-domain")
            require(row["capture_error"] is None, "capture-error")
            require(all(integer(row[k], 0, 2**63 - 1) for k in ("qpc_before_ticks", "qpc_after_ticks")), "counter-integer")
            require(all(integer(row[k], 0, 2**32 - 1) for k in ("filetime_low", "filetime_high")), "filetime-integer")
            require(integer(row["utc_ns"], 0, 253402300799999999900), "utc-integer-or-range")
            require(row["utc_ns"] == (((row["filetime_high"] << 32) | row["filetime_low"]) - EPOCH_TICKS) * 100, "filetime-conversion")
            low, high = row["qpc_before_ticks"], row["qpc_after_ticks"]
            require(low <= high and (index == 1 or low >= self.points[-2]["qpc_after_ticks"]), "counter-reversal-or-overlap")
            span = (high - low + 2) * NS
            r["max_bracket_ns_ceil"] = max(r["max_bracket_ns_ceil"], (span + f - 1) // f)
            require(span <= MAX_BRACKET_NS * f, "bracket-too-wide")
            for prior in self.points[:-1]:
                against = prior["sequence"]
                delta = (row["utc_ns"] - prior["utc_ns"]) * f
                allowance = 2 * UTC_READ_ALLOWANCE_NS * f + 2 * NS
                lower = delta - (high - prior["qpc_before_ticks"]) * NS - allowance
                upper = delta - (low - prior["qpc_after_ticks"]) * NS + allowance
                r["comparisons"] += 1
                r["max_abs_residual_ns_ceil"] = max(r["max_abs_residual_ns_ceil"], (max(abs(lower), abs(upper)) + f - 1) // f)
                require(lower <= TOLERANCE_NS * f and upper >= -TOLERANCE_NS * f, "clock-discontinuity-observed")
                require(lower >= -TOLERANCE_NS * f and upper <= TOLERANCE_NS * f, "clock-consistency-ambiguous")
            r["accepted_points"] += 1
            r["clock_capture_valid"] = index >= 2
        except ValueError as exc:
            r["clock_capture_valid"] = False
            r["rejection"] = dict(code=str(exc), sequence=index, against_sequence=against)
        return self.status()

    def status(self):
        # The primitive's minimum-two-points rule applies to a public report.
        if len(self.points) < 2:
            return dict(clock_capture_valid=False, accepted_points=0, comparisons=0,
                        max_bracket_ns_ceil=0, max_abs_residual_ns_ceil=0,
                        rejection=dict(code="point-count", sequence=None, against_sequence=None))
        return copy.deepcopy(self.report)


class Journal:
    """One domain, durable attempts and a nonrenewable cleanup reserve.

    Checkpoints may be shared by adjacent *capture envelopes*. They must not
    be described as the actual dispatch/exit instants. A future command adapter
    must prove containment inside the referenced raw brackets using same-domain
    QPC dispatch/exit ticks, charge intervening overhead and enforce deadlines.
    This component does not make that command-containment claim.
    """
    def __init__(self, clock, path):
        self.clock = clock
        self.prefix = Prefix(clock.descriptor)
        self.path = Path(path)
        self.handle = self.path.open("xb")
        self.events, self.failure = [], None
        self.capture_failed = False
        self.closed = False
        try:
            self._emit(dict(kind="header", contract_id=CONTRACT_ID,
                            descriptor=self.prefix.descriptor, admission_point_limit=ADMISSION_POINT_LIMIT,
                            reserved_cleanup_points=RESERVED_CLEANUP_POINTS, max_points=MAX_POINTS))
        except BaseException:
            self.close()
            raise

    def _emit(self, event):
        event = copy.deepcopy(event)
        event["event"] = len(self.events) + 1
        self.events.append(event)
        try:
            self.handle.write((json.dumps(event, allow_nan=False) + "\n").encode())
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except BaseException as exc:
            self.failure = self.failure or ("journal-write: " + type(exc).__name__ + ": " + str(exc))
            raise

    def checkpoint(self, label, *, cleanup=False):
        if self.closed or type(label) is not str or not label or len(label) > 128 or type(cleanup) is not bool:
            raise ValueError("checkpoint contract")
        reason = None
        if self.failure:
            reason = "latched-journal-failure"
        elif self.capture_failed:
            reason = "capture-source-unavailable"
        elif len(self.prefix.points) >= (MAX_POINTS if cleanup else ADMISSION_POINT_LIMIT):
            reason = "point-capacity" if cleanup else "cleanup-reserve"
        elif not cleanup and self.prefix.report["rejection"] is not None:
            reason = "latched-clock-rejection"
        if reason:
            self._emit(dict(kind="blocked", label=label, cleanup=cleanup, reason=reason))
            return None
        try:
            # Never retry a thrown API read: its internal sequence may have been
            # consumed without returning a point. Preserve that missingness.
            point = self.clock.capture()
        except BaseException as exc:
            self.capture_failed = True
            self._emit(dict(kind="source-error", label=label, cleanup=cleanup,
                            error=type(exc).__name__ + ": " + str(exc)))
            return None
        report = self.prefix.add(point)
        self._emit(dict(kind="point", label=label, cleanup=cleanup, point=point))
        return len(self.prefix.points) if report["clock_capture_valid"] else None

    def admitted(self, *, points_needed=1):
        require(type(points_needed) is int and 1 <= points_needed <= ADMISSION_POINT_LIMIT, "admission reservation")
        return bool(not self.closed and not self.failure and not self.capture_failed
                    and self.prefix.status()["clock_capture_valid"]
                    and len(self.prefix.points) + points_needed <= ADMISSION_POINT_LIMIT)

    def snapshot(self):
        return dict(contract_id=CONTRACT_ID, descriptor=copy.deepcopy(self.prefix.descriptor),
                    points=copy.deepcopy(self.prefix.points), events=copy.deepcopy(self.events),
                    reported=self.prefix.status(), journal_failure=self.failure,
                    capture_source_failed=self.capture_failed, admission_open=self.admitted() if not self.closed else False)

    def close(self):
        # Do not fabricate a completion timestamp or silently repair a short file.
        try:
            self.handle.close()
        finally:
            self.closed = True


def attempt_cleanup_steps(journal, steps):
    """Exception-isolated dispatch plumbing, NOT authority to perform actions.

    Only the future approval/scope-checked caller can supply an official cleanup
    plan. Here tests supply local callbacks with no I/O. No success claim about
    service restoration follows from callbacks returning.
    """
    require(type(steps) is list and 1 <= len(steps) <= 64, "cleanup step inventory")
    require(all(type(name) is str and name and len(name) <= 100 and callable(fn) for name, fn in steps)
            and len({name for name, _ in steps}) == len(steps), "unique cleanup steps")
    result = []
    for name, callback in steps:
        row = dict(name=name, attempted=False, callback_returned=False, errors=[])
        for phase in ("before", "callback", "after"):
            try:
                if phase == "callback":
                    row["attempted"] = True
                    callback()
                    row["callback_returned"] = True
                else:
                    reference = journal.checkpoint("cleanup:" + name + ":" + phase, cleanup=True)
                    if reference is None:
                        row["errors"].append(phase + ": timestamp unaccepted or unavailable")
            except BaseException as exc:
                row["errors"].append(phase + ": " + type(exc).__name__ + ": " + str(exc))
        result.append(row)
    return dict(steps=result, all_callbacks_attempted=all(r["attempted"] for r in result),
                service_restored=False, network_fix_validated=False)
