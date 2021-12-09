import atexit
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Any, Callable, Dict, List, Optional

import yaml

from kentik_synth_client import KentikAPIRequestError, SynTest, TestStatus
from synth_tools import log
from synth_tools.apis import APIs
from synth_tools.test_factory import TestFactory


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


@dataclass
class ErrorRecord:
    type: str
    cause: Any

    def to_dict(self) -> Dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}


class TestRunStatus(Enum):
    NONE = "none"
    SUCCESS = "success"
    CONFIG_BUILD_FAILED = "config build failed"
    CREATION_FAILED = "creation failed"
    NO_HEALTH_DATA = "no health data"
    DELETE_FAILED = "test delete failed"
    STATUS_CHANGE_FAILED = "status change failed"
    RETRYABLE_ERROR = "retryable error"
    OTHER = "other"


class TestResults:
    def __init__(
        self,
        test: Optional[SynTest] = None,
    ):
        self.test = test
        if self.test:
            self.test_id = self.test.id  # test.id is reset when test is un-deployed
        else:
            self.test_id = ""
        self.polls = 0
        self.errors: List[ErrorRecord] = list()
        self.results: Dict[str, Any] = defaultdict(list)
        self.status = TestRunStatus.NONE

    def set_health(self, health):
        self.status = TestRunStatus.SUCCESS
        for task in health["tasks"]:
            for agent in task["agents"]:
                for h in agent["health"]:
                    for task_type in ("ping", "knock", "shake", "dns", "http"):
                        if task_type in task["task"]:
                            if task_type == "dns":
                                target = (
                                    f"{task['task'][task_type]['target']} via {task['task'][task_type]['resolver']}"
                                )
                            else:
                                target = task["task"][task_type]["target"]
                            break
                    else:
                        target = h["dstIp"]
                        task_type = h["taskType"]
                    e = dict(
                        time=h["overallHealth"]["time"],
                        agent_id=agent["agent"]["id"],
                        agent_addr=agent["agent"]["ip"],
                        task_type=task_type,
                        loss=f"{h['packetLoss'] * 100}% ({h['packetLossHealth']})",
                        latency=f"{h['avgLatency']/1000}ms ({h['latencyHealth']})",
                        jitter=f"{h['avgJitter']/1000}ms ({h['jitterHealth']})",
                    )
                    for field in ("data", "status", "size"):
                        if field in h:
                            e[field] = h[field]
                    data = e.get("data")
                    if data:
                        try:
                            e["data"] = json.loads(data)
                        except json.decoder.JSONDecodeError as ex:
                            log.critical("Failed to parse JSON in health data '%s' (exception: %s)", data, ex)
                    self.results[target].append(e)
        for entries in self.results.values():
            entries.sort(key=lambda x: x["time"])

    def record_error(self, status: TestRunStatus, label: str, cause: Any):
        self.status = status
        self.errors.append(ErrorRecord(label, cause))

    @property
    def test_type(self) -> str:
        return self.test.type.value if self.test else ""

    @property
    def test_name(self) -> str:
        return self.test.name if self.test else ""

    @property
    def test_targets(self) -> List[str]:
        return self.test.targets if self.test else []

    @property
    def test_agents(self) -> List[str]:
        return self.test.settings.agentIds if self.test else []

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            status=self.status.name,
            test=dict(
                id=self.test_id,
                type=self.test_type,
                name=self.test_name,
                targets=self.test_targets,
                agents=self.test_agents,
            ),
            execution=dict(
                polls=self.polls,
                results=dict(self.results),
            ),
            errors=[e.to_dict() for e in self.errors],
        )


def run_one_shot(api: APIs, test: SynTest, retries: int = 3, delete: bool = True) -> TestResults:
    r = TestResults(test)

    def _delete_test(tst: SynTest) -> bool:
        log.debug("Deleting test '%s' (id: %s)", tst.name, tst.id)
        try:
            api.syn.delete_test(tst.id)
            log.info("Deleted test %s' (id: %s)", tst.name, tst.id)
            return True
        except Exception as ex:
            r.record_error(TestRunStatus.DELETE_FAILED, "API_ERROR: TestDelete", ex)
            log.error("Failed to delete test '%s' (id: %s) (%s)", tst.name, tst.id, ex)
            return False

    def _pause_test(tst: SynTest) -> bool:
        log.info("Pausing test id: %s", tst.id)
        try:
            api.syn.set_test_status(tst.id, TestStatus.paused)
            return True
        except Exception as ex:
            r.record_error(TestRunStatus.STATUS_CHANGE_FAILED, "API_ERROR: TestStatusUpdate", ex)
            log.error("Failed to pause test '%s' (id: %s) (%s)", tst.name, tst.id, ex)
            return False

    log.debug("creating test '%s'", test.name)
    try:
        t = api.syn.create_test(test)
        # make sure that we do not leave detritus behind if execution is terminated prematurely
        atexit.register(_delete_test, t)
    except Exception as exc:
        r.record_error(TestRunStatus.CREATION_FAILED, "API_ERROR: TestCreate", exc)
        log.error("Failed to create test '%s' (%s)", test.name, exc)
        return r
    log.info("Created test '%s' (id: %s)", t.name, t.id)
    r.test_id = t.id  # Must save here, because test delete resets it
    if t.status != TestStatus.active:
        log.info("Activating test '%s'", t.name)
        try:
            api.syn.set_test_status(t.id, TestStatus.active)
        except Exception as exc:
            r.record_error(TestRunStatus.STATUS_CHANGE_FAILED, "API_ERROR: TestStatusUpdate", exc)
            log.error("tid: %s Failed to activate test (%s)", t.id, exc)
            return r

    wait_time = max(
        0.0,
        t.max_period,
    )
    start = datetime.now(tz=timezone.utc)
    while retries:
        if wait_time > 0:
            log.debug("tid: %s: Waiting %s seconds for test to accumulate results", t.id, wait_time)
            sleep(wait_time)
        wait_time = t.max_period
        now = datetime.now(tz=timezone.utc)
        try:
            r.polls += 1
            health = api.syn.health(
                [t.id],
                start=min(start, now - timedelta(seconds=t.max_period)),
                end=now,
            )
        except KentikAPIRequestError as exc:
            r.record_error(TestRunStatus.RETRYABLE_ERROR, "API_ERROR: GetHealthForTests", exc)
            log.error("tid: %s Failed to retrieve test health (%s). Retrying ...", t.id, exc)
            retries -= 1
            continue
        except Exception as exc:
            r.record_error(TestRunStatus.NO_HEALTH_DATA, "API_ERROR: GetHealthForTests", exc)
            log.error("tid: %s Failed to retrieve test health (%s). Giving up.", t.id, exc)
            break
        if len(health) < 1:
            log.debug("tid: %s Health not available after %f seconds", t.id, (now - start).total_seconds())
            retries -= 1
            continue
        health_ts = datetime.fromisoformat(health[0]["overallHealth"]["time"].replace("Z", "+00:00"))
        if (health_ts - now).total_seconds() > t.max_period:
            log.info(
                "tid: %s Stale health data after %f second (timestamp: %s)",
                t.id,
                (now - start).total_seconds(),
                health_ts.isoformat(),
            )
            retries -= 1
            continue
        r.set_health(health[0])
        log.debug(
            "tid: %s %s at %s",
            t.id,
            health[0]["overallHealth"]["health"],
            health_ts.isoformat(),
        )
        break
    else:
        r.record_error(TestRunStatus.NO_HEALTH_DATA, "TIMEOUT", f"Failed to get valid health data")
        log.debug("tid: %s Failed to get valid health data for test", t.id)

    if delete:
        all_clean = _delete_test(t)
    else:
        all_clean = _pause_test(t)
    if all_clean:
        atexit.unregister(_delete_test)
    log.debug("tid: %s status: %s errors: %d", r.status, len(r.errors))
    return r


def load_test(api: APIs, file: Path, fail: Callable[[str], None] = _fail) -> Optional[SynTest]:
    if file.exists():
        if not file.is_file():
            fail(f"Test configuration '{file.as_posix()}' is not a file")
    else:
        fail(f"Test configuration file '{file.as_posix()}' does not exist")
    log.info("Loading test configuration from '%s'", file.as_posix())
    try:
        with file.open() as f:
            cfg = yaml.safe_load(f)
    except Exception as ex:
        fail(f"Failed to load test config: {ex}")
    test = TestFactory().create(api, file.stem, cfg, fail)
    if not test:
        log.debug("Failed to create test")  # never reached, TestFactory.create does not return without valid test
    else:
        log.debug("loaded test: '%s'", ", ".join(f"{k}:{v}" for k, v in test.to_dict().items()))
    return test
