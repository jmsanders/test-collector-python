"""Buildkite Test Engine payload"""

from dataclasses import dataclass, replace, field
from typing import Dict, Tuple, Optional, Union, Literal, List, Iterable, Mapping
from datetime import timedelta
from uuid import UUID

from ..pytest_plugin.logger import logger

from .instant import Instant
from .run_env import RunEnv

JsonValue = Union[str, int, float, bool, 'JsonDict', Tuple['JsonValue']]
JsonDict = Dict[str, JsonValue]

# pylint: disable=C0103 disable=W0622 disable=R0913


@dataclass(frozen=True)
class TestResultPassed:
    """Represents a passed test result"""


@dataclass(frozen=True)
class TestResultFailed:
    """Represents a failed test result"""
    failure_reason: Optional[str]
    failure_expanded: Optional[Iterable[Mapping[str, Iterable[str]]]] = None


@dataclass(frozen=True)
class TestResultSkipped:
    """Represents a skipped test"""


@dataclass(frozen=True)
class TestSpan:
    """
    A test span.

    Buildkite Test Analtics supports some basic tracing to allow insight into
    the runtime performance your tests.
    """
    section: Literal['http', 'sql', 'sleep', 'annotation']
    duration: timedelta
    start_at: Optional[Instant] = None
    end_at: Optional[Instant] = None
    detail: Optional[str] = None

    def as_json(self, started_at: Instant) -> JsonDict:
        """Convert this span into a Dict for eventual serialisation into JSON"""
        attrs = {
            "section": self.section,
            "duration": self.duration.total_seconds()
        }

        if self.detail is not None:
            attrs["detail"] = self.detail

        if self.start_at is not None:
            attrs["start_at"] = (self.start_at - started_at).total_seconds()

        if self.end_at is not None:
            attrs["end_at"] = (self.end_at - started_at).total_seconds()

        return attrs


@dataclass(frozen=True)
class TestHistory:
    """
    The timings of the test execution.

    Buildkite Test Analtics supports some basic tracing to allow insight into
    the runtime performance your tests.  This object is the top-level of that
    tracing tree.
    """
    start_at: Optional[Instant] = None
    end_at: Optional[Instant] = None
    duration: Optional[timedelta] = None
    children: List['TestSpan'] = ()

    def is_finished(self) -> bool:
        """Is there an end_at time present?"""
        return self.end_at is not None

    def push_span(self, span: TestSpan) -> 'TestHistory':
        """Add a new span to the children"""
        return replace(self, children=self.children + tuple([span]))

    def as_json(self, started_at: Instant) -> JsonDict:
        """Convert this trace into a Dict for eventual serialisation into JSON"""
        attrs = {
            "section": "top",
            "children": list(map(lambda span: span.as_json(started_at), self.children))
        }

        if self.start_at is not None:
            attrs["start_at"] = (self.start_at - started_at).total_seconds()

        if self.end_at is not None:
            attrs["end_at"] = (self.end_at - started_at).total_seconds()

        if self.duration is not None:
            attrs["duration"] = self.duration.total_seconds()

        return attrs


@dataclass(frozen=True)
class TestData:
    """An individual test execution"""
    # 8 attributes for this class seems reasonable
    # pylint: disable=too-many-instance-attributes
    id: UUID
    scope: str
    name: str
    history: TestHistory
    location: Optional[str] = None
    file_name: Optional[str] = None
    tags: Dict[str,str] = field(default_factory=dict)
    result: Union[TestResultPassed, TestResultFailed,
                  TestResultSkipped, None] = None

    @classmethod
    def start(cls, id: UUID,
              *,
              scope: str,
              name: str,
              location: Optional[str] = None,
              file_name: Optional[str] = None) -> 'TestData':
        """Build a new instance with it's start_at time set to now"""
        return cls(
            id=id,
            scope=scope,
            name=name,
            location=location,
            file_name=file_name,
            history=TestHistory(start_at=Instant.now())
        )

    def tag_execution(self, key: str, val: str) -> 'TestData':
        """Set tag to test execution"""
        if not isinstance(key, str) or not isinstance(val, str):
            raise TypeError("Expected string for key and value")

        new_tags = self.tags.copy()
        new_tags[key] = val
        return replace(self, tags=new_tags)

    def finish(self) -> 'TestData':
        """Set the end_at and duration on this test"""
        if self.is_finished():
            return self

        end_at = Instant.now()
        duration = end_at - self.history.start_at
        return replace(self, history=replace(self.history,
                                             end_at=end_at,
                                             duration=duration))

    def passed(self) -> 'TestData':
        """Mark this test as passed"""
        return replace(self, result=TestResultPassed())

    def failed(self, failure_reason=None, failure_expanded=None) -> 'TestData':
        """Mark this test as failed"""
        result = TestResultFailed(failure_reason=failure_reason, failure_expanded=failure_expanded)
        return replace(self, result=result)

    def skipped(self) -> 'TestData':
        """Mark this test as skipped"""
        return replace(self, result=TestResultSkipped())

    def is_finished(self) -> bool:
        """Does this test have an end_at time?"""
        return self.history and self.history.is_finished()

    def push_span(self, span: TestSpan) -> 'TestData':
        """Add a span to the test history"""
        return replace(self, history=self.history.push_span(span))

    def as_json(self, started_at: Instant) -> JsonDict:
        """Convert into a Dict suitable for eventual serialisation to JSON"""
        attrs = {
            "id": str(self.id),
            "scope": self.scope,
            "name": self.name,
            "location": self.location,
            "file_name": self.file_name,
            "history": self.history.as_json(started_at)
        }

        if len(self.tags) > 0:
            attrs["tags"] = self.tags

        if isinstance(self.result, TestResultPassed):
            attrs["result"] = "passed"

        if isinstance(self.result, TestResultFailed):
            attrs["result"] = "failed"
            if self.result.failure_reason is not None:
                attrs["failure_reason"] = self.result.failure_reason
            if self.result.failure_expanded is not None:
                attrs["failure_expanded"] = self.result.failure_expanded

        if isinstance(self.result, TestResultSkipped):
            attrs["result"] = "skipped"

        return attrs


@dataclass(frozen=True)
class Payload:
    """The full test analytics payload"""
    run_env: RunEnv
    data: Tuple[TestData]
    started_at: Optional[Instant]
    finished_at: Optional[Instant]

    @classmethod
    def init(cls, run_env: RunEnv) -> 'Payload':
        """Create a new instance of payload with the provided RunEnv"""

        return cls(
            run_env=run_env,
            data=(),
            started_at=None,
            finished_at=None
        )

    def as_json(self) -> JsonDict:
        """Convert into a Dict suitable for eventual serialisation to JSON"""
        finished_data = list(filter(
            lambda td: td.is_finished(),
            self.data
        ))

        if len(finished_data) < len(self.data):
            logger.warning('Unexpected unfinished test data, skipping unfinished test records...')

        return {
            "format": "json",
            "run_env": self.run_env.as_json(),
            "data": tuple(map(lambda td: td.as_json(self.started_at), finished_data)),
        }

    def push_test_data(self, report: TestData) -> 'Payload':
        """Append a test-data to the payload"""
        return replace(self, data=self.data + tuple([report]))

    def is_started(self) -> bool:
        """Returns true of the payload has been started"""
        return self.started_at is not None

    def started(self) -> 'Payload':
        """Mark the payload as started (ie the suite has started)"""
        return replace(self, started_at=Instant.now())

    def into_batches(self, batch_size=100) -> Tuple['Payload']:
        """Convert the payload into a collection of payloads based on the batch size"""
        return self.__into_batches(self.data, tuple(), batch_size)

    def __into_batches(self, data, batches, batch_size) -> Tuple['Payload']:
        if len(data) <= batch_size:
            return batches + tuple([replace(self, data=data)])

        next_batch = data[0:batch_size]
        next_data = data[batch_size:]
        return self.__into_batches(
            next_data,
            batches + tuple([replace(self, data=next_batch)]), batch_size)
