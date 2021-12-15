import re
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from itertools import product
from typing import Any, Callable, Dict, List, Optional

from synth_tools import log
from synth_tools.utils import fail


class Matcher(ABC):
    SPECIAL = {
        "all": "AllMatcher",
        "any": "AnyMatcher",
        "one_of_each": "OneOfEachMatcher",
    }

    @abstractmethod
    def match(self, data: object) -> bool:
        raise NotImplementedError


class PropertyMatcher(Matcher):
    class MatchFunctionType(Enum):
        direct = 0
        regex = "regex"
        contains = "contains"
        one_of = "one_of"
        older_than = "older_than"
        newer_than = "newer_than"

    def __init__(self, key: str, value: Any, property_transformer: Optional[Callable[[str], str]] = None):
        self.match_type = self.MatchFunctionType.direct
        self.value: Any = value
        if property_transformer:
            self.key = property_transformer(key)
        else:
            self.key = key
        self._fn = self._match_direct
        self.is_negation = False
        # handle special functions
        if type(self.value) == str:
            if self.value.startswith("!"):
                self.is_negation = True
                self.value = self.value[1:]
            m = re.match(
                r"({})\((.*)\)".format("|".join([t.value for t in self.MatchFunctionType if t.value])), self.value
            )
            if m:
                try:
                    self.match_type = self.MatchFunctionType(m.group(1))
                except ValueError:
                    log.debug(
                        "%s: unknown match function '%s' - treating as direct", self.__class__.__name__, m.group(1)
                    )
                if self.match_type == self.MatchFunctionType.regex:
                    self.value = re.compile(m.group(2))
                    self._fn = self._match_regex
                elif self.match_type == self.MatchFunctionType.contains:
                    self.value = m.group(2)
                    self._fn = self._match_contains
                elif self.match_type == self.MatchFunctionType.one_of:
                    self.value = [s.strip() for s in m.group(2).split(",")]
                    self._fn = self._match_one_of
                elif self.match_type == self.MatchFunctionType.older_than:
                    self._value_from_ts(m.group(2))
                    self._fn = self._match_older_than
                elif self.match_type == self.MatchFunctionType.newer_than:
                    self._value_from_ts(m.group(2))
                    self._fn = self._match_newer_than
        log.debug(
            "%s: key: '%s' value: '%s' match_type: '%s' is_negation: '%s'",
            self.__class__.__name__,
            self.key,
            self.value,
            self.match_type.value,
            self.is_negation,
        )

    def match(self, data: Any) -> bool:
        log.debug("%s: matching key: '%s', data: '%s'", self.__class__.__name__, self.key, str(data))
        # handle special properties
        if self.key == "label" and hasattr(data, "has_label"):
            log.debug("%s: matching label", self.__class__.__name__)
            return self._match_label(data) ^ self.is_negation

        key_path = self.key.split(".")
        obj = data
        k = self.key  # to make linters happy
        while key_path:
            k = key_path.pop(0)
            log.debug("%s: matching k: '%s', obj: '%s'", self.__class__.__name__, k, str(obj))
            if hasattr(obj, k):
                obj = getattr(obj, k)
            elif k in obj:  # type: ignore
                obj = obj[k]  # type: ignore
            else:
                log.debug(
                    "%s: object: does not have property '%s'", self.__class__.__name__, self.key
                )
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        if isinstance(obj, Enum):
            v = obj.value
        else:
            v = obj
        log.debug(
            "%s: matching '%s' '%s': '%s', value: '%s'", self.__class__.__name__, k, self.match_type.name, self.value, v
        )
        ret = self._fn(v) ^ self.is_negation
        log.debug("%s: ret %s", self.__class__.__name__, ret)
        return ret

    def _match_label(self, obj: Any) -> bool:
        if self.match_type == self.MatchFunctionType.direct:
            ret = obj.has_label(self.value)  # type: ignore
        elif self.match_type == self.MatchFunctionType.one_of:
            ret = any(obj.has_label(label) for label in self.value)
        else:
            log.error(
                "'%s' function is not supported for matching attribute 'label' of '%s'",
                self.match_type.name,
                obj.__class__.__name__,
            )
            ret = self.is_negation
        log.debug("%s: ret '%s'", self.__class__.__name__, ret)
        return ret

    def _match_direct(self, obj: Any) -> bool:
        return str(obj) == str(self.value)

    def _match_regex(self, obj: Any) -> bool:
        # noinspection PyUnresolvedReferences
        return self.value.match(str(obj)) is not None

    def _match_contains(self, obj: Any) -> bool:
        if type(obj) == str:
            return self.value in obj
        if hasattr(obj, "__iter__"):
            log.debug("%s: '%s' is iterable", self.__class__.__name__, obj)
            return self.value in [str(x) for x in obj]
        else:
            return self.value == obj or str(self.value) == str(obj)

    def _match_one_of(self, obj: Any) -> bool:
        return any(str(obj) == v for v in self.value)

    def _match_older_than(self, obj: Any) -> bool:
        if not self.value:
            # config had invalid time specification, nothing can match
            return False
        ts = self._ts_from_string(str(obj))
        if not ts:
            log.error("%s: Cannot parse time: '%s'", self.__class__.__name__, str(obj))
            return self.is_negation
        else:
            return ts < self.value  # type:ignore

    def _match_newer_than(self, obj: Any) -> bool:
        if not self.value:
            # config had invalid time specification, nothing can match
            return False
        ts = self._ts_from_string(str(obj))
        if not ts:
            log.error("%s: Cannot parse time: '%s'", self.__class__.__name__, str(obj))
            return self.is_negation
        else:
            return ts > self.value  # type:ignore

    @staticmethod
    def _ts_from_string(s: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        if s.endswith("Z"):
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00").replace("T", " "))
            except ValueError:
                return None
        else:
            return None

    def _value_from_ts(self, arg: str) -> None:
        if arg == "now":
            self.value = datetime.now(tz=timezone.utc)
        elif arg == "today":
            self.value = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        elif arg == "yesterday":
            self.value = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=1
            )
        elif arg == "tomorrow":
            self.value = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
        else:
            try:
                self.value = datetime.fromisoformat(arg)
                if not self.value.tzinfo:
                    log.debug("Setting timezone to UTC for match time '%s'", self.value.isoformat())
                    self.value = self.value.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                log.error("%s: Invalid timestamp in configuration: %s", self.__class__.__name__, exc)
                self.value = None


class SetMatcher(Matcher):
    def __init__(
        self,
        data: List[Dict[str, Any]],
        max_matches: Optional[int] = None,
        property_transformer: Optional[Callable[[str], str]] = None,
    ):
        self.matchers = []
        self.max_matches: Optional[int] = max_matches
        self._done = False
        if type(data) != list:
            raise RuntimeError(f"Invalid match specification: {data}")
        for e in data:
            if type(e) != dict:
                raise RuntimeError(f"Invalid match specification: {data}")
            for k, v in e.items():
                if k in self.SPECIAL:
                    matcher = getattr(sys.modules[__name__], self.SPECIAL[k])(v)
                else:
                    matcher = PropertyMatcher(k, v, property_transformer=property_transformer)
                self.matchers.append(matcher)
        log.debug("%s: %d matchers, max_matches: %s", self.__class__.__name__, len(self.matchers), self.max_matches)

    def match(self, data: object) -> bool:
        if self._done:
            return False
        if self.max_matches is not None and self.max_matches == 0:
            log.debug("%s: match limit reached", self.__class__.__name__)
            self._done = True
            return False
        return self.do_match(data)

    @abstractmethod
    def do_match(self, data: object) -> bool:
        raise NotImplementedError


class AllMatcher(SetMatcher):
    def do_match(self, data: object) -> bool:
        for m in self.matchers:
            if not m.match(data):
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        log.debug("%s: ret '%s'", self.__class__.__name__, True)
        if self.max_matches is not None:
            self.max_matches -= 1
        return True


class AnyMatcher(SetMatcher):
    def do_match(self, data: object) -> bool:
        if not self.matchers:
            log.debug("%s: no matchers: ret '%s'", self.__class__.__name__, True)
            if self.max_matches is not None:
                self.max_matches -= 1
            return True
        for m in self.matchers:
            if m.match(data):
                log.debug("%s: ret '%s'", self.__class__.__name__, True)
                if self.max_matches is not None:
                    self.max_matches -= 1
                return True
        log.debug("%s: ret '%s'", self.__class__.__name__, False)
        return False


class OneOfEachMatcher(Matcher):
    def __init__(self, data: Dict[str, List]):
        self.match_vector = data.keys()
        self.match_set = set([tuple(x) for x in product(*[data[k] for k in self.match_vector])])
        log.debug(
            "%s: match_set: '%s'",
            self.__class__.__name__,
            ", ".join("|".join(str(e) for e in x) for x in self.match_set),
        )

    def match(self, data: Any) -> bool:
        if not self.match_set:
            return False
        m = tuple(data[k] for k in self.match_vector)
        log.debug("%s: matching: '%s'", self.__class__.__name__, ", ".join(str(x) for x in m))
        if m in self.match_set:
            self.match_set.remove(m)
            log.debug("%s: remaining %d in match_set", self.__class__.__name__, len(self.match_set))
            ret = True
        else:
            ret = False
        log.debug("%s: ret '%s'", self.__class__.__name__, ret)
        return ret


def all_matcher_from_rules(rules: List[str]) -> AllMatcher:
    log.debug("rules: '%s'", rules)
    matchers: List[Dict] = []
    for r in rules:
        parts = r.split(":", maxsplit=1)
        if len(parts) != 2:
            fail(f"Invalid match spec: {r} (must have format: '<property>:<value>')")
        matchers.append({parts[0]: parts[1]})
    return AllMatcher(matchers)
