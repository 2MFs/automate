import json
import sys
import types
from unittest import mock

import pytest

from automate.providers.base import ChatMessage, ToolSpec


def _install_litellm_stub():
    fake = types.ModuleType("litellm")
    fake.completion = mock.MagicMock(name="litellm.completion")
    sys.modules["litellm"] = fake
    return fake


@pytest.fixture(autouse=True)
def litellm_stub():
    fake = _install_litellm_stub()
    yield fake
    sys.modules.pop("litellm", None)


def _mock_response(content: str = "Hello!", tool_calls=None):
    from types import SimpleNamespace

    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_chat_calls_litellm_completion(litellm_stub):
    litellm_stub.completion.return_value = _mock_response("reply")

    from automate.providers.litellm import LiteLLMClient

    client = LiteLLMClient(model="anthropic/claude-haiku-4-5", api_key="sk-test")
    resp = client.chat(
        [ChatMessage(role="user", content="Hi")],
        model="anthropic/claude-haiku-4-5",
    )

    litellm_stub.completion.assert_called_once()
    kwargs = litellm_stub.completion.call_args.kwargs
    assert kwargs["model"] == "anthropic/claude-haiku-4-5"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["drop_params"] is True
    assert resp.content == "reply"


def test_chat_omits_blank_credentials(litellm_stub):
    litellm_stub.completion.return_value = _mock_response()

    from automate.providers.litellm import LiteLLMClient

    client = LiteLLMClient(model="openai/gpt-4o")
    client.chat([ChatMessage(role="user", content="Hi")], model="openai/gpt-4o")

    kwargs = litellm_stub.completion.call_args.kwargs
    assert "api_key" not in kwargs
    assert "api_base" not in kwargs


def test_chat_forwards_tools(litellm_stub):
    litellm_stub.completion.return_value = _mock_response()

    from automate.providers.litellm import LiteLLMClient

    tool = ToolSpec(name="search", description="Search the web", parameters={"type": "object", "properties": {}})
    client = LiteLLMClient(model="openai/gpt-4o", api_key="k")
    client.chat(
        [ChatMessage(role="user", content="Find info")],
        model="openai/gpt-4o",
        tools=[tool],
    )

    kwargs = litellm_stub.completion.call_args.kwargs
    assert kwargs["tool_choice"] == "auto"
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0]["function"]["name"] == "search"


def test_chat_parses_tool_call_response(litellm_stub):
    from types import SimpleNamespace

    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="search", arguments=json.dumps({"q": "test"})),
    )
    litellm_stub.completion.return_value = _mock_response("", tool_calls=[tc])

    from automate.providers.litellm import LiteLLMClient

    client = LiteLLMClient(model="openai/gpt-4o", api_key="k")
    resp = client.chat(
        [ChatMessage(role="user", content="Hi")],
        model="openai/gpt-4o",
    )

    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "search"
    assert resp.tool_calls[0].arguments == {"q": "test"}


def test_catalog_contains_litellm():
    from automate.providers.catalog import get_spec

    spec = get_spec("litellm")
    assert spec is not None
    assert spec.adapter == "litellm"
