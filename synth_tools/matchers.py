import logging
import re
import sys
from abc import ABC, abstractmethod
from enum import Enum
from itertools import product
from typing import Any, Dict, List

log = logging.getLogger("matcher")


class Matcher(ABC):
    SPECIAL = {
        "match_all": "AllMatcher",
        "match_any": "AnyMatcher",
        "one_of_each": "OneOfEachMatcher",
    }

    @abstractmethod
    def match(self, data: object) -> bool:
        raise NotImplementedError


class PropertyMatcher(Matcher):
    def __init__(self, key: str, value: Any):
        self.is_regex = False
        self.key = key
        if type(value) == str:
            m = re.match(r"regex\((.*)\)", value)
        else:
            m = None
        if m:
            self.value = re.compile(m.groups()[0])
            self.is_regex = True
        else:
            self.value = value

    def match(self, data: object) -> bool:
        # handle exceptions
        if self.key == "label" and hasattr(data, "has_label"):
            log.debug("%s: matching label: '%s', data: '%s'", self.__class__.__name__, self.value, str(data))
            ret = data.has_label(self.value)
            log.debug("%s: ret '%s'", self.__class__.__name__, ret)
            return ret
        log.debug("%s: matching key: '%s', data: '%s'", self.__class__.__name__, self.key, str(data))
        key_path = self.key.split(".")
        obj = data
        while key_path:
            k = key_path.pop(0)
            log.debug("%s: matching k: '%s', value: '%s'", self.__class__.__name__, k, str(obj))
            if hasattr(obj, k):
                obj = getattr(obj, k)
            elif k in obj:
                obj = obj[k]
            else:
                log.warning(
                    "%s: object: '%s' does not have property '%s'", self.__class__.__name__, str(data), self.key
                )
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        if type(obj) == str and self.is_regex:
            log.debug("%s: matching regex: '%s', value: '%s'", self.__class__.__name__, self.value, obj)
            ret = self.value.match(obj) is not None
        elif isinstance(obj, Enum):
            ret = obj.value == self.value
        else:
            ret = obj == self.value
        log.debug("%s: ret %s", self.__class__.__name__, ret)
        return ret


class SetMatcher(Matcher):
    def __init__(self, data: List[Dict[str, Any]]):
        self.matchers = []
        for e in data:
            for k, v in e.items():
                if k in self.SPECIAL:
                    matcher = getattr(sys.modules[__name__], self.SPECIAL[k])(v)
                else:
                    matcher = PropertyMatcher(k, v)
                self.matchers.append(matcher)
        log.debug("%s: %d matchers", self.__class__.__name__, len(self.matchers))

    @abstractmethod
    def match(self, data: object) -> bool:
        return super().match(data)


class AllMatcher(SetMatcher):
    def match(self, data: object) -> bool:
        for m in self.matchers:
            if not m.match(data):
                log.debug("%s: ret '%s'", self.__class__.__name__, False)
                return False
        log.debug("%s: ret '%s'", self.__class__.__name__, True)
        return True


class AnyMatcher(SetMatcher):
    def match(self, data: object) -> bool:
        if not self.matchers:
            log.debug("%s: no matchers: ret '%s'", self.__class__.__name__, True)
            return True
        for m in self.matchers:
            if m.match(data):
                log.debug("%s: ret '%s'", self.__class__.__name__, True)
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

    def match(self, data: Dict[str, Any]) -> bool:
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
