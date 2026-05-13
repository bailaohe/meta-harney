from meta_harney.builtin.trace.null_sink import NullSink
from tests.contracts.trace_sink import TraceSinkContract


class TestNullSink(TraceSinkContract):
    def make_sink(self) -> NullSink:
        return NullSink()
