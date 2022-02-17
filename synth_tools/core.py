import atexit
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Any, Callable, Dict, List, Optional

import yaml

from kentik_synth_client import KentikAPIRequestError
from kentik_synth_client.synth_tests import SynTest
from kentik_synth_client.types import TestStatus
from synth_tools import log
from synth_tools.apis import APIs
from synth_tools.test_factory import TestFactory
from synth_tools.utils import camel_to_snake, transform_dict_keys


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
    NO_RESULTS = "no results"
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
        self.results: List[Dict[str, Any]] = list()
        self.status = TestRunStatus.NONE

    def set_results(self, results: List[Dict[str, Any]]):
        def _metric_data(m: str, d: Dict[str, Any]) -> str:
            unit = ""
            factor = 1
            if m == "packet_loss":
                unit = "%"
                factor = 100.0
            elif m in ("latency", "jitter"):
                unit = "ms"
                factor = 0.001
            else:
                log.error("Unknown metric '%s' in results", m)
            v = float(d["current"]) * factor
            out = f"{v:.5}{unit}"
            for stat in ("avg", "stddev"):
                s = f"rolling_{stat}"
                if s in d:
                    v = float(d[s]) * factor
                    out += f" {stat}: {v:.5}{unit}"
            out += f" ({d['health']})"
            return out

        self.status = TestRunStatus.SUCCESS
        for entry in transform_dict_keys(results, camel_to_snake):
            log.debug("entry: %s", entry)
            if entry["test_id"] != self.test_id:
                log.warning("TestResults[tid: %s]: Ignoring results for test ID '%s'", self.test_id, entry["test_id"])
                continue
            e = dict(
                time=entry["time"],
                health=entry["health"],
                agents=list(),
            )
            self.results.append(e)
            for agent in entry["agents"]:
                a = dict(
                    id=agent["agent_id"],
                    health=agent["health"],
                    tasks=list(),
                )
                e["agents"].append(a)
                for task in agent["tasks"]:
                    for task_type in ("ping", "http", "dns"):
                        if task_type in task:
                            break
                    else:
                        log.error("No data for any of test tasks (%s) in results", ",".join(self.test.configured_tasks))
                        continue
                    td = task[task_type]
                    if not td["target"]:
                        td["target"] = ",".join(self.test.targets)
                    if "server" in td:
                        target = f"{td['target']} via {td['server']}"
                    elif "dst_ip" in td:
                        target = f"{td['target']} [{td['dst_ip']}]"
                    else:
                        target = td["target"]
                    if not target:
                        target = self.test_targets[0]
                    t = dict(
                        type=task_type,
                        target=target,
                    )
                    a["tasks"].append(t)
                    for metric in ("packet_loss", "latency", "jitter"):
                        if metric in td:
                            t[metric] = _metric_data(metric, td[metric])
                    r = td.get("response")
                    if r:
                        t["response"] = r
                        if "data" in r:
                            try:
                                r["data"] = transform_dict_keys(json.loads(r["data"])[0], camel_to_snake)
                            except json.decoder.JSONDecodeError as ex:
                                log.critical("Failed to parse JSON in results data '%s' (exception: %s)", r, ex)
        self.results.sort(key=lambda x: x["time"])

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
                results=self.results,
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

    wait_time = float(t.settings.period)
    start = datetime.now(tz=timezone.utc)
    while retries:
        log.debug("tid: %s: Waiting %s seconds for test to accumulate results", t.id, wait_time)
        sleep(wait_time)
        now = datetime.now(tz=timezone.utc)
        try:
            r.polls += 1
            data = api.syn.results(
                t,
                start=min(start, now - timedelta(seconds=t.settings.period)),
                end=now,
            )
        except KentikAPIRequestError as exc:
            r.record_error(TestRunStatus.RETRYABLE_ERROR, "API_ERROR: GetHealthForTests", exc)
            log.error("tid: %s Failed to retrieve test health (%s). Retrying ...", t.id, exc)
            retries -= 1
            continue
        except Exception as exc:
            r.record_error(TestRunStatus.NO_RESULTS, "API_ERROR: GetResultsForTests", exc)
            log.error("tid: %s Failed to retrieve test results (%s). Giving up.", t.id, exc)
            break
        if len(data) < 1:
            log.debug("tid: %s Results not available after %f seconds", t.id, (now - start).total_seconds())
            retries -= 1
            continue
        results_ts = datetime.fromisoformat(data[0]["time"].replace("Z", "+00:00"))
        if results_ts < start:
            log.info(
                "tid: %s Stale results data after %f second (timestamp: %s, test start: %s)",
                t.id,
                (now - start).total_seconds(),
                results_ts.isoformat(),
                start,
            )
            retries -= 1
            continue
        r.set_results(data)
        log.debug(
            "tid: %s %s at %s",
            t.id,
            data[0]["health"],
            results_ts.isoformat(),
        )
        break
    else:
        r.record_error(TestRunStatus.NO_RESULTS, "TIMEOUT", f"Failed to get valid results")
        log.debug("tid: %s Failed to get valid results for test", t.id)

    if delete:
        all_clean = _delete_test(t)
    else:
        all_clean = _pause_test(t)
    if all_clean:
        atexit.unregister(_delete_test)
    log.debug("tid: %s status: %s errors: %d", r.test_id, r.status, len(r.errors))
    return r


def expand_values(data: dict, subs: Dict[str, str]) -> None:
    def _expand(d: Any) -> Any:
        if type(d) == dict:
            for k, v in d.items():
                d[k] = _expand(v)
            return d
        elif type(d) == list:
            out = list()
            for e in d:
                out.append(_expand(e))
            return out
        elif type(d) == str:
            log.debug("d: %s", d)
            n = d
            for k, v in subs.items():
                n = n.replace(k, v)
            if d != n:
                log.debug(
                    "expanded: '%s' to '%s'",
                    d,
                    n,
                )
            return n
        else:
            return d

    log.debug("expand_values: subs: %s", " ".join(f"{k}:{v}" for k, v in subs.items()))
    _expand(data)


def load_test(
    api: APIs, file: Path, subs: Optional[Dict[str, str]] = None, fail: Callable[[str], None] = _fail
) -> Optional[SynTest]:
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
    if subs:
        expand_values(cfg, subs)
    test = TestFactory().create(api, file.stem, cfg, fail)
    if not test:
        log.debug("Failed to create test")  # never reached, TestFactory.create does not return without valid test
    else:
        log.debug("loaded test: '%s'", ", ".join(f"{k}:{v}" for k, v in test.to_dict().items()))
    return test
