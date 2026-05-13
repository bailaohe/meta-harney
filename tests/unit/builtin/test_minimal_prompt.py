from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.prompt_builder import PromptBuilderContract


class TestMinimalPromptBuilder(PromptBuilderContract):
    def make_store(self):
        return MemorySessionStore()

    def make_builder(self, store):
        return MinimalPromptBuilder(session_store=store)


# Builder-specific tests:


async def test_default_system_prompt_content():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(session_store=store)
    sp = await builder.build_system_prompt("any")
    assert "helpful ai assistant" in sp.lower()


async def test_custom_system_prompt_override():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(
        session_store=store,
        system_prompt="You are a billing specialist.",
    )
    sp = await builder.build_system_prompt("any")
    assert sp == "You are a billing specialist."
