import logging
import re
import sys
from abc import ABC, abstractmethod
from enum import Enum
from itertools import product
from typing import Any, Dict, List, Optional

log = logging.getLogger("matchers")


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
        regex = 1
        contains = 2
        one_of = 3

    MATCH_FUNCTIONS = {
        "regex": MatchFunctionType.regex,
        "contains": MatchFunctionType.contains,
        "one_of": MatchFunctionType.one_of,
    }

    def __init__(self, key: str, value: Any):
        self.match_type = self.MatchFunctionType.direct
        self.value: Any
        self.key = key
        # handle special functions
        if type(value) == str:
            m = re.match(r"({})\((.*)\)".format("|".join(self.MATCH_FUNCTIONS.keys())), value)
            if m:
                self.match_type = self.MATCH_FUNCTIONS.get(m.group(1), self.MatchFunctionType.direct)
                if self.match_type == self.MatchFunctionType.regex:
                    self.value = re.compile(m.group(2))
                elif self.match_type == self.MatchFunctionType.contains:
                    self.value = m.group(2)
                elif self.match_type == self.MatchFunctionType.one_of:
                    self.value = [s.strip() for s in m.group(2).split(",")]
        if self.match_type == self.MatchFunctionType.direct:
            self.value = value
        log.debug(
            "%s: key: '%s' value: '%s' match_type: '%s'", self.__class__.__name__, self.key, self.value, self.match_type
        )

    def match(self, data: Any) -> bool:
        ret = False
        # handle exceptions
        if self.key == "label" and hasattr(data, "has_label"):
            log.debug("%s: matching label: '%s', data: '%s'", self.__class__.__name__, self.value, str(data))
            if self.match_type == self.MatchFunctionType.direct:
                ret = data.has_label(self.value)  # type: ignore
            elif self.match_type == self.MatchFunctionType.one_of:
                ret = any(data.has_label(label) for label in self.value)
            else:
                log.error(
                    "'%s' function is not supported for matching attribute 'label' of '%s'",
                    self.match_type.name,
                    data.__class__.__name__,
                )
                ret = False
            log.debug("%s: ret '%s'", self.__class__.__name__, ret)
            return ret
        log.debug("%s: matching key: '%s', data: '%s'", self.__class__.__name__, self.key, str(data))
        key_path = self.key.split(".")
        obj = data
        while key_path:
            k = key_path.pop(0)
            log.debug("%s: matching k: '%s', obj: '%s'", self.__class__.__name__, k, str(obj))
            if hasattr(obj, k):
                obj = getattr(obj, k)
            elif k in obj:  # type: ignore
                obj = obj[k]  # type: ignore
            else:
                log.warning(
                    "%s: object: '%s' does not have property '%s'", self.__class__.__name__, str(data), self.key
                )
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        if isinstance(obj, Enum):
            v = obj.value
        else:
            v = obj
        log.debug("%s: matching '%s': '%s', value: '%s'", self.__class__.__name__, self.match_type.name, self.value, v)
        if self.match_type == self.MatchFunctionType.direct:
            ret = str(obj) == str(self.value)
        elif self.match_type == self.MatchFunctionType.regex:
            ret = self.value.match(str(v)) is not None
        elif self.match_type == self.MatchFunctionType.contains:
            if hasattr(v, "__iter__"):
                log.debug("%s: '%s' is iterable", self.__class__.__name__, v)
                ret = self.value in v
            else:
                ret = self.value == v or str(self.value) == str(v)
        elif self.match_type == self.MatchFunctionType.one_of:
            ret = any(str(obj) == v for v in self.value)
        log.debug("%s: ret %s", self.__class__.__name__, ret)
        return ret


class SetMatcher(Matcher):
    def __init__(self, data: List[Dict[str, Any]], max_matches: Optional[int] = None):
        self.matchers = []
        self.max_matches: Optional[int] = max_matches
        for e in data:
            for k, v in e.items():
                if k in self.SPECIAL:
                    matcher = getattr(sys.modules[__name__], self.SPECIAL[k])(v)
                else:
                    matcher = PropertyMatcher(k, v)
                self.matchers.append(matcher)
        log.debug("%s: %d matchers, max_matches: %s", self.__class__.__name__, len(self.matchers), self.max_matches)

    @abstractmethod
    def match(self, data: object) -> bool:
        return super().match(data)


class AllMatcher(SetMatcher):
    def match(self, data: object) -> bool:
        if self.max_matches is not None and self.max_matches == 0:
            log.debug("%s: match limit reached", self.__class__.__name__)
            return False
        for m in self.matchers:
            if not m.match(data):
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        log.debug("%s: ret '%s'", self.__class__.__name__, True)
        if self.max_matches is not None:
            self.max_matches -= 1
        return True


class AnyMatcher(SetMatcher):
    def match(self, data: object) -> bool:
        if self.max_matches is not None and self.max_matches == 0:
            log.debug("%s: match limit reached", self.__class__.__name__)
            return False
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
