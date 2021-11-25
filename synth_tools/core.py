import atexit
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Any, Callable, Dict, Optional, Tuple

import yaml

from kentik_synth_client import KentikAPIRequestError, SynTest, TestStatus
from synth_tools.apis import APIs
from synth_tools.test_factory import TestFactory

log = logging.getLogger("core")


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


class TestResults:
    def __init__(
        self,
        test: SynTest,
        test_id: Optional[str] = None,
        polls: Optional[int] = None,
        health: Optional[Dict[str, Any]] = None,
    ):
        self.test_id = test_id
        self.name = test.name
        self.type = test.type.value
        self.agents = test.settings.agentIds
        self.polls = polls
        self.targets: Dict[str, Any] = defaultdict(list)
        self.success = health is not None
        if not health:
            return
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
                    self.targets[target].append(e)

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            success=self.success,
            id=self.test_id,
            name=self.name,
            agents=self.agents,
            polls=self.polls,
            targets={k: v for k, v in self.targets.items()},
        )


def run_one_shot(
    api: APIs,
    test: SynTest,
    wait_factor: float = 1.0,
    retries: int = 3,
    delete: bool = True,
) -> Tuple[Optional[str], Optional[int], Optional[dict]]:
    def _delete_test(tst: SynTest) -> bool:
        log.debug("Deleting test '%s' (id: %s)", tst.name, tst.id)
        try:
            api.syn.delete_test(tst.id)
            log.info("Deleted test %s' (id: %s)", tst.name, tst.id)
            return True
        except KentikAPIRequestError as exc:
            log.error("Failed to delete test '%s' (id: %s) (%s)", tst.name, tst.id, exc)
            return False

    def _pause_test(tst: SynTest) -> bool:
        log.info("Pausing test id: %s", tst.id)
        try:
            api.syn.set_test_status(tst.id, TestStatus.paused)
            return True
        except KentikAPIRequestError as exc:
            log.error("Failed to pause test '%s' (id: %s) (%s)", tst.name, tst.id, exc)
            return False

    polls = 0
    log.debug("creating test '%s'", test.name)
    try:
        t = api.syn.create_test(test)
        # make sure that we do not leave detritus behind if execution is terminated prematurely
        atexit.register(_delete_test, t)
    except KentikAPIRequestError as ex:
        log.error("Failed to create test '%s' (%s)", test.name, ex)
        return None, None, None
    log.info("Created test '%s' (id: %s)", t.name, t.id)
    tid = t.id  # Must save here, because test delete resets it
    if t.status != TestStatus.active:
        log.info("Activating test '%s'", t.name)
        try:
            api.syn.set_test_status(t.id, TestStatus.active)
        except KentikAPIRequestError as ex:
            log.error("tid: %s Failed to activate test (%s)", tid, ex)
            return tid, None, None

    wait_time = max(
        0.0,
        t.max_period * wait_factor,
    )
    start = datetime.now(tz=timezone.utc)
    while retries:
        if wait_time > 0:
            log.info("tid: %s: Waiting %s seconds for test to accumulate results", tid, wait_time)
            sleep(wait_time)
        wait_time = t.max_period * 1.0
        now = datetime.now(tz=timezone.utc)
        try:
            polls += 1
            health = api.syn.health(
                [t.id],
                start=min(start, now - timedelta(seconds=t.max_period * wait_factor)),
                end=now,
            )
        except KentikAPIRequestError as ex:
            log.error("tid: %s Failed to retrieve test health (%s). Retrying ...", tid, ex)
            retries -= 1
            continue
        if len(health) < 1:
            log.debug("tid: %s Health not available after %f seconds", tid, (now - start).total_seconds())
            retries -= 1
            continue
        health_ts = datetime.fromisoformat(health[0]["overallHealth"]["time"].replace("Z", "+00:00"))
        if (health_ts - now).total_seconds() > t.max_period * wait_factor:
            log.info(
                "tid: %s Stale health data after %f second (timestamp: %s)",
                tid,
                (now - start).total_seconds(),
                health_ts.isoformat(),
            )
            retries -= 1
            continue
        log.debug(
            "tid: %s %s at %s",
            tid,
            health[0]["overallHealth"]["health"],
            health_ts.isoformat(),
        )
        break
    else:
        log.debug("tid: %s Failed to get valid health data for test", tid)
        health = None, tid, polls

    if delete:
        all_clean = _delete_test(t)
    else:
        all_clean = _pause_test(t)
    if all_clean:
        atexit.unregister(_delete_test)
    log.debug("tid: %s polls: %d health: %s", tid, polls, health)
    return tid, polls, health[0] if health else None


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
