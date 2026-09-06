"""Prospective runner budget/health/settling plumbing, without execution authority.

Only a caller-provided frozen transport and same-domain wait callback are used.
No process, socket, native clock, image, restart or power API is created here.
"""
import copy
import json

CONTRACT_ID = "safetwin5g-reconnect-r5-budget-v1"
TARGETS = ("safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue")


def require(value, message):
    if not value:
        raise ValueError(message)


def inventory():
    """Prospective operation counts, not measured or implemented whole-run work."""
    def reset(targets, polls):
        return 4+targets*(polls+2)  # four prefix/identity commands; restart + health + terminal
    def switch(polls):
        return 2*(2+polls+1)  # independently inspect/apply each image + health terminal
    def trial(polls, qdisc):
        return 3+reset(3, polls)+60+1+2+1+1+1+60+2+qdisc
    def ladder(polls):
        return reset(1, polls)+60+reset(3, polls)+60
    rollback = dict(owned_qdisc=3, both_image_attempts=switch(25), post_image_scope=2,
                    independent_reset=reset(3, 25), three_packet_telemetry_windows=60,
                    final_scope=2, final_eth0=1, final_telemetry=4, host_close=2, execution_terminal=1)
    normal_nominal = 5+12+switch(1)+2+4*trial(1, 1)+2*(reset(1, 1)+60)
    # This sums both restoration arms for every assignment without early-stop
    # pruning: an upper envelope, NOT a feasible positive execution trajectory.
    normal_upper = 5+12+switch(25)+2+4*(trial(25, 3)+ladder(25))
    maximum_cleanup = sum(rollback.values())
    return dict(contract_id=CONTRACT_ID, normal_limit=768, total_limit=1024, reserved_cleanup=256,
                health_max_polls=25, health_waits_max=24, health_points_max=26,
                collection_with_telemetry_points=20, normal_nominal_points=normal_nominal,
                unpruned_normal_upper_points=normal_upper, cleanup_point_terms=rollback,
                cleanup_points_max=maximum_cleanup, admitted_prefix_plus_cleanup_max=768+maximum_cleanup,
                capacity_headroom=1024-768-maximum_cleanup, packet_identifier_upper_unpruned=4*12+3,
                guarantees_four_complete_trials=False, runner_implemented=False,
                whole_protocol_verified=False, network_execution_authorized=False, evidence_label="fixture")


class RunnerBudget:
    def __init__(self, journal, transport, wait_ms):
        require(transport.journal is journal and transport.clock is journal.clock and callable(wait_ms), "same-domain budget transport/wait required")
        require(journal.admitted(points_needed=1), "two accepted bootstrap points required")
        self.journal, self.transport, self.clock, self.wait_ms = journal, transport, journal.clock, wait_ms
        self.descriptor = copy.deepcopy(journal.prefix.descriptor)
        self.last_tick, self.counter_error, self.active = None, None, False
        self.start_point = len(journal.prefix.points)
        self.global_deadline = journal.prefix.points[-1]["qpc_before_ticks"]+1500*self.descriptor["frequency_hz"]
        self.operations, self.admissions = [], []

    def _tick(self):
        if self.counter_error is None:
            try:
                require(json.dumps(self.clock.descriptor, sort_keys=True) == json.dumps(self.descriptor, sort_keys=True), "changed budget domain")
                value = self.clock.ticks()
                require(type(value) is int and 0 <= value < 2**63 and (self.last_tick is None or value >= self.last_tick), "invalid/reversing budget counter")
                self.last_tick = value
                return value
            except BaseException as exc:
                self.counter_error = type(exc).__name__+": "+str(exc)
        return None

    def admit(self, label, *, points_needed, seconds_needed):
        require(type(label) is str and 0 < len(label) <= 80 and type(points_needed) is int and 1 <= points_needed <= 768
                and type(seconds_needed) is int and 1 <= seconds_needed <= 1500, "prospective admission request")
        j, tick = self.journal, self._tick()
        row = dict(label=label, point=len(j.prefix.points), event=len(j.events), ticks=tick, points_needed=points_needed,
                   seconds_needed=seconds_needed, global_deadline_ticks=self.global_deadline, counter_error=self.counter_error, admitted=False)
        row["admitted"] = bool(tick is not None and j.admitted(points_needed=points_needed)
                               and tick >= j.prefix.points[-1]["qpc_after_ticks"] and tick+seconds_needed*self.descriptor["frequency_hz"] <= self.global_deadline)
        self.admissions.append(row)
        return copy.deepcopy(row)

    def _start(self, kind, label, cleanup):
        require(not self.active and type(cleanup) is bool and type(label) is str and 0 < len(label) <= 80, "once-at-a-time timing operation")
        self.active = True
        j = self.journal
        w = dict(number=len(self.operations)+1, kind=kind, label=label, cleanup=cleanup, start_point=len(j.prefix.points),
                 start_event=len(j.events), deadline_ticks=None, checks=[], commands=[], waits=[], final_ticks=None,
                 end_point=None, terminal_before=None, terminal_after=None, counter_error=None, errors=[], accepted=False)
        self.operations.append(w)
        return w

    def _finish(self, w):
        j = self.journal
        w["final_ticks"], w["terminal_before"] = self._tick(), len(j.events)
        before = len(j.prefix.points)
        try:
            j.checkpoint("budget:"+str(w["number"])+":end", cleanup=w["cleanup"])
        except BaseException as exc:
            w["errors"].append("terminal: "+type(exc).__name__+": "+str(exc))
        w["terminal_after"] = len(j.events)
        w["end_point"] = len(j.prefix.points) if len(j.prefix.points) > before else None
        w["counter_error"] = self.counter_error
        p = j.prefix.points[-1] if w["end_point"] else None
        valid = bool(not self.counter_error and not j.failure and not j.capture_failed and j.prefix.status()["clock_capture_valid"]
                     and p and type(w["final_ticks"]) is int and w["final_ticks"] <= p["qpc_before_ticks"])
        if w["kind"] == "health":
            valid = bool(valid and w["deadline_ticks"] is not None and p["qpc_after_ticks"] < w["deadline_ticks"])
        if not w["cleanup"]:
            valid = bool(valid and p and p["qpc_after_ticks"] < self.global_deadline)
        if not valid:
            w["errors"].append("terminal timing rejected")
        w["accepted"] = bool(not w["errors"])
        self.active = False
        return copy.deepcopy(w)

    def _wait(self, w, milliseconds):
        j, f = self.journal, self.descriptor["frequency_hz"]
        r = dict(milliseconds=milliseconds, event=len(j.events), point=len(j.prefix.points), before_ticks=self._tick(),
                 after_ticks=None, called=False, returned=False, error=None)
        w["waits"].append(r)
        try:
            require(r["before_ticks"] is not None, "wait counter unavailable")
            r["called"] = True
            self.wait_ms(milliseconds)
            r["returned"] = True
        except BaseException as exc:
            r["error"] = type(exc).__name__+": "+str(exc)
        r["after_ticks"] = self._tick()
        require(r["error"] is None and r["returned"] and r["after_ticks"] is not None
                and (r["after_ticks"]-r["before_ticks"])*1000 >= milliseconds*f, "wait failed or returned early")

    def settle(self, label="post-exposure"):
        w = self._start("settle", label, False)
        try:
            a = self.admit(label, points_needed=1, seconds_needed=5)
            w["checks"].append(a)
            require(a["admitted"], "settling admission rejected")
            self._wait(w, 5000)
        except BaseException as exc:
            w["errors"].append(type(exc).__name__+": "+str(exc))
        return self._finish(w)

    def health(self, container, *, cleanup=False):
        require(container in TARGETS, "health target outside fixed scope")
        w = self._start("health", container, cleanup)
        j, f = self.journal, self.descriptor["frequency_hz"]
        anchor = j.prefix.points[-1] if j.prefix.points else None
        w["deadline_ticks"] = anchor["qpc_before_ticks"]+50*f if anchor and type(anchor["qpc_before_ticks"]) is int else None
        try:
            # Reserve the whole prospective health operation, not its first poll.
            tick = self._tick()
            initial = dict(ticks=tick, event=len(j.events), point=len(j.prefix.points), points_needed=26,
                           admitted=bool(tick is not None and not j.failure and not j.capture_failed and j.prefix.status()["clock_capture_valid"]
                                         and len(j.prefix.points)+26 <= (1024 if cleanup else 768)
                                         and tick >= j.prefix.points[-1]["qpc_after_ticks"] and w["deadline_ticks"] is not None
                                         and tick < w["deadline_ticks"] and (cleanup or tick+50*f <= self.global_deadline)))
            w["checks"].append(initial)
            require(initial["admitted"], "health admission rejected")
            for poll in range(25):
                tick = self._tick()
                p = j.prefix.points[-1]
                due = w["deadline_ticks"] if cleanup else min(w["deadline_ticks"], self.global_deadline)
                timeout = min(35000, (due-p["qpc_before_ticks"])*1000//f) if type(p["qpc_before_ticks"]) is int else None
                admitted = bool(tick is not None and not j.failure and not j.capture_failed and j.prefix.status()["clock_capture_valid"]
                                and p["qpc_after_ticks"] <= tick < due and timeout is not None and timeout >= 1)
                w["checks"].append(dict(ticks=tick, event=len(j.events), point=len(j.prefix.points), poll=poll+1, timeout_ms=timeout, admitted=admitted))
                require(admitted, "health poll admission rejected")
                argv = ["docker", "inspect", "--format", "{{.State.Health.Status}}", container]
                sequence = self.transport.next_sequence
                row = self.transport.run(argv, sequence=sequence, timeout_ms=timeout, max_output_bytes=1048576, cleanup=cleanup)
                w["commands"].append(row)
                require(type(row["sequence"]) is int and row["sequence"] == sequence and row["argv"] == argv and row["cleanup"] is cleanup and row["timeout_ms"] == timeout and row["max_output_bytes"] == 1048576
                        and row["complete"] is True and type(row["returncode"]) is int and row["returncode"] == 0
                        and row["stdout_utf8"] is True and row["stderr_utf8"] is True and row["stderr"] == "", "health client rejected")
                status = row["stdout"].strip()
                require(status in ("healthy", "starting", "unhealthy"), "health status unsupported")
                if status == "healthy":
                    break
                if poll == 24:
                    raise TimeoutError("health poll inventory exhausted")
                self._wait(w, 2000)
            else:
                raise TimeoutError("health poll inventory exhausted")
        except BaseException as exc:
            w["errors"].append(type(exc).__name__+": "+str(exc))
        return self._finish(w)

    def snapshot(self):
        return dict(contract_id=CONTRACT_ID, clock_id=self.descriptor["clock_id"], start_point=self.start_point,
                    global_deadline_ticks=self.global_deadline, admissions=copy.deepcopy(self.admissions), operations=copy.deepcopy(self.operations),
                    counter_error=self.counter_error, whole_protocol_verified=False, network_execution_authorized=False,
                    rollback_verified=False, network_fix_validated=False)


if __name__ == "__main__":
    raise SystemExit("No execution CLI; this timing/inventory component is not a full runner or approval gate.")
