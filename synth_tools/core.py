import atexit
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Callable, Optional

import yaml

from kentik_synth_client import KentikAPIRequestError, SynTest, TestStatus
from synth_tools.apis import APIs
from synth_tools.test_factory import TestFactory

log = logging.getLogger("core")


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


def run_one_shot(
    api: APIs,
    test: SynTest,
    wait_factor: float = 1.0,
    retries: int = 3,
    delete: bool = True,
) -> Optional[dict]:
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

    log.debug("creating test '%s'", test.name)
    try:
        t = api.syn.create_test(test)
        # make sure that we do not leave detritus behind if execution is terminated prematurely
        atexit.register(_delete_test, t)
    except KentikAPIRequestError as ex:
        log.error("Failed to create test '%s' (%s)", test.name, ex)
        return None
    log.info("Created test '%s' (id: %s)", t.name, t.id)
    if t.status != TestStatus.active:
        log.info("Activating test '%s'", t.name)
        try:
            api.syn.set_test_status(t.id, TestStatus.active)
        except KentikAPIRequestError as ex:
            log.error("Failed to activate test '%s' (id: %s) (%s)", t.name, t.id, ex)
            return None

    wait_time = max(
        0.0,
        t.max_period * wait_factor,
    )
    start = datetime.now(tz=timezone.utc)
    while retries:
        if wait_time > 0:
            log.info("Waiting for %s seconds for test to accumulate results", wait_time)
            sleep(wait_time)
        wait_time = t.max_period * 1.0
        now = datetime.now(tz=timezone.utc)
        try:
            health = api.syn.health(
                [t.id],
                start=min(start, now - timedelta(seconds=t.max_period * wait_factor)),
                end=now,
            )
        except KentikAPIRequestError as ex:
            log.error("Failed to retrieve test health (%s). Retrying ...", ex)
            retries -= 1
            continue
        if len(health) < 1:
            log.debug("Health not available after %f seconds", (now - start).total_seconds())
            retries -= 1
            continue
        health_ts = datetime.fromisoformat(health[0]["overallHealth"]["time"].replace("Z", "+00:00"))
        if (health_ts - now).total_seconds() > t.max_period * wait_factor:
            log.info(
                "Stale health data after %f second (timestamp: %s)",
                (now - start).total_seconds(),
                health_ts.isoformat(),
            )
            retries -= 1
            continue
        log.debug(
            "Test '%s' is %s at %s",
            t.id,
            health[0]["overallHealth"]["health"],
            health_ts.isoformat(),
        )
        break
    else:
        log.debug("Failed to get valid health data for test id: %s", t.id)
        health = None

    if delete:
        all_clean = _delete_test(t)
    else:
        all_clean = _pause_test(t)
    if all_clean:
        atexit.unregister(_delete_test)
    return health[0] if health else None


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
