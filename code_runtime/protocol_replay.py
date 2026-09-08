"""Server-owned native response blocks and bounded protocol history projection."""
import copy
import hashlib
import json
import re
from .reasoning_capabilities import ReasoningError

LIMIT = 16 * 1024 * 1024


def fail():
    raise ReasoningError("reasoning_replay_invalid")


def clone(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > LIMIT:
        raise ReasoningError("reasoning_replay_limit")
    return json.loads(encoded)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def kind(snapshot):
    if not snapshot or snapshot.get("schemaVersion") != 3:
        return ""
    return "deepseek" if snapshot["protocolProfile"] == "deepseek-chat-v4-v1" else "claude"


def scope(snapshot, payload):
    return digest([snapshot, [m for m in payload.get("messages", []) if m.get("role") in {"system", "developer"}],
                   payload.get("tools", []), payload.get("thinking"), payload.get("output_config"),
                   payload.get("reasoning_effort")])


def public_message(message):
    return {k: copy.deepcopy(v) for k, v in message.items() if k in {"role", "content", "tool_calls", "tool_call_id"}}


def normalize(value, snapshot):
    if not kind(snapshot):
        if value is not None:
            fail()
        return None
    if not isinstance(value, dict) or set(value) != {"version", "kind", "entries"}:
        fail()
    if value["version"] != 1 or value["kind"] != kind(snapshot) or not isinstance(value["entries"], dict):
        fail()
    for ref, entry in value["entries"].items():
        if (not re.fullmatch(r"[a-f0-9]{32}:[1-9][0-9]*", ref)
                or not isinstance(entry, dict) or set(entry) != {"scope", "history", "message", "native"}
                or not isinstance(entry["scope"], str) or len(entry["scope"]) != 64
                or not isinstance(entry["history"], str) or len(entry["history"]) != 64
                or not isinstance(entry["message"], dict) or entry["message"].get("role") != "assistant"):
            fail()
        validate_native(value["kind"], entry["native"], entry["message"])
    return clone(value)


def empty(snapshot):
    return {"version": 1, "kind": kind(snapshot), "entries": {}} if kind(snapshot) else None


def validate_native(protocol, native, message):
    if protocol == "deepseek":
        if not isinstance(native, dict) or set(native) != {"reasoning_content"} or not isinstance(native["reasoning_content"], str):
            fail()
        return
    if not isinstance(native, list) or not native:
        fail()
    texts, calls = [], []
    for block in native:
        if not isinstance(block, dict):
            fail()
        t = block.get("type")
        if t == "thinking":
            if (set(block) != {"type", "thinking", "signature"} or not isinstance(block["thinking"], str)
                    or not isinstance(block["signature"], str) or not block["signature"]):
                fail()
        elif t == "redacted_thinking":
            if set(block) != {"type", "data"} or not isinstance(block["data"], str) or not block["data"]:
                fail()
        elif t == "text":
            if not isinstance(block.get("text"), str):
                fail()
            texts.append(block["text"])
        elif t == "tool_use":
            if not isinstance(block.get("input"), dict) or not block.get("id") or not block.get("name"):
                fail()
            calls.append((block["id"], block["name"], block["input"]))
        else:
            fail()
    expected = []
    for call in message.get("tool_calls", []):
        try:
            expected.append((call["id"], call["function"]["name"], json.loads(call["function"]["arguments"])))
        except (KeyError, ValueError, TypeError):
            fail()
    if "".join(texts) != message.get("content", "") or calls != expected:
        fail()


class Response:
    """Strict SSE assembler. Opaque thinking/signatures never enter public events."""
    def __init__(self, protocol):
        self.protocol = protocol
        self.blocks = {}
        self.open_blocks = set()
        self.partial = {}
        self.reasoning = ""
        self.reasoning_seen = False
        self.finished = False
        self.stopped = False
        self.started = False
        self.bytes = 0
        self.finish_reason = None

    def feed(self, data):
        self.bytes += len(data.encode("utf-8"))
        if self.bytes > LIMIT:
            raise ReasoningError("reasoning_replay_limit")
        if data == "[DONE]":
            if not self.finished:
                fail()
            self.stopped = True
            return data
        try:
            frame = json.loads(data)
        except (ValueError, TypeError):
            fail()
        if self.protocol == "deepseek":
            choices = frame.get("choices") or []
            if choices:
                choice = choices[0]
                message = choice.get("delta", choice.get("message", {}))
                if "reasoning_content" in message:
                    value = message["reasoning_content"]
                    if value is not None:
                        if not isinstance(value, str):
                            fail()
                        self.reasoning_seen = True
                        self.reasoning += value
                if choice.get("finish_reason") is not None:
                    self.finished = True
                    self.finish_reason = choice["finish_reason"]
            return data
        t = frame.get("type")
        delta = {}
        usage = {}
        finish = None
        if t == "message_start":
            if self.started:
                fail()
            self.started = True
            usage = frame.get("message", {}).get("usage", {})
        elif t == "content_block_start":
            index = frame.get("index")
            if not self.started or type(index) is not int or index != len(self.blocks):
                fail()
            block = copy.deepcopy(frame.get("content_block"))
            if not isinstance(block, dict):
                fail()
            self.blocks[index] = block
            self.open_blocks.add(index)
            if block.get("type") == "tool_use":
                delta = {"tool_calls": [{"index": index, "id": block.get("id"), "type": "function",
                                           "function": {"name": block.get("name"), "arguments": ""}}]}
            elif block.get("type") == "text":
                delta = {"content": block.get("text", "")}
            elif block.get("type") == "thinking":
                delta = {"reasoning_content": block.get("thinking", "")}
        elif t == "content_block_delta":
            index = frame.get("index")
            if index not in self.open_blocks:
                fail()
            block = self.blocks[index]
            change = frame.get("delta", {})
            dt = change.get("type")
            field = {"thinking_delta": "thinking", "signature_delta": "signature", "text_delta": "text"}.get(dt)
            if field:
                expected = "text" if field == "text" else "thinking"
                if block.get("type") != expected or not isinstance(change.get(field), str):
                    fail()
                block[field] = block.get(field, "") + change[field]
                if field == "text":
                    delta["content"] = change[field]
                elif field == "thinking":
                    delta["reasoning_content"] = change[field]
            elif dt == "input_json_delta" and block.get("type") == "tool_use":
                part = change.get("partial_json")
                if not isinstance(part, str):
                    fail()
                self.partial[index] = self.partial.get(index, "") + part
                delta = {"tool_calls": [{"index": index, "function": {"arguments": part}}]}
            else:
                fail()
        elif t == "content_block_stop":
            index = frame.get("index")
            if index not in self.open_blocks:
                fail()
            if index in self.partial:
                try:
                    self.blocks[index]["input"] = json.loads(self.partial[index])
                except ValueError:
                    fail()
            elif self.blocks[index].get("type") == "tool_use":
                delta = {"tool_calls": [{"index": index, "function": {"arguments": json.dumps(self.blocks[index].get("input", {}))}}]}
            self.open_blocks.remove(index)
        elif t == "message_delta":
            if self.open_blocks or not self.started:
                fail()
            finish = frame.get("delta", {}).get("stop_reason")
            self.finished = finish is not None
            self.finish_reason = finish
            usage = frame.get("usage", {})
        elif t == "message_stop":
            if not self.finished or self.open_blocks:
                fail()
            self.stopped = True
            return "[DONE]"
        elif t != "ping":
            fail()
        if usage:
            usage = {**usage, **({"prompt_tokens": usage["input_tokens"]} if "input_tokens" in usage else {}),
                     **({"completion_tokens": usage["output_tokens"]} if "output_tokens" in usage else {})}
        return json.dumps({"choices": [{"delta": delta, "finish_reason": finish}], "usage": usage})

    def complete(self, message):
        if not self.stopped or not self.finished:
            fail()
        if message.get("tool_calls") and self.finish_reason not in {"tool_use", "tool_calls"}:
            fail()
        if self.protocol == "deepseek":
            if not self.reasoning_seen:
                fail()
            native = {"reasoning_content": self.reasoning}
        else:
            native = [self.blocks[i] for i in sorted(self.blocks)]
        validate_native(self.protocol, native, message)
        return clone(native)


def _content(value):
    if isinstance(value, str):
        return [{"type": "text", "text": value}] if value else []
    result = []
    for block in value or []:
        if block.get("type") == "text":
            result.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "image_url":
            url = block["image_url"]["url"]
            if url.startswith("data:") and ";base64," in url:
                mime, data = url[5:].split(";base64,", 1)
                result.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
            elif url.startswith("https://"):
                result.append({"type": "image", "source": {"type": "url", "url": url}})
            else:
                fail()
        else:
            fail()
    return result


def messages_request(payload):
    """Compile the Code-owned Chat-shaped internal request to native Messages."""
    allowed = {"model", "max_tokens", "thinking", "output_config", "temperature", "top_p", "top_k", "stream"}
    wire = {k: copy.deepcopy(v) for k, v in payload.items() if k in allowed}
    if type(wire.get("max_tokens")) is not int or wire["max_tokens"] <= 0:
        raise ReasoningError("reasoning_budget_insufficient")
    budget = wire.get("thinking", {}).get("budget_tokens")
    if budget is not None and wire["max_tokens"] < budget + 1024:
        raise ReasoningError("reasoning_budget_insufficient")
    system, messages = [], []
    for message in payload.get("messages", []):
        role = message["role"]
        if role in {"system", "developer"}:
            system.extend(_content(message.get("content", "")))
            continue
        if role == "tool":
            role = "user"
            blocks = [{"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message.get("content", "")}]
        else:
            blocks = copy.deepcopy(message.get("_nativeBlocks")) if "_nativeBlocks" in message else _content(message.get("content", ""))
            if "_nativeBlocks" not in message:
                for call in message.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": call["id"], "name": call["function"]["name"],
                                   "input": json.loads(call["function"]["arguments"])})
        if not blocks:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(blocks)
        else:
            messages.append({"role": role, "content": blocks})
    wire["messages"] = messages
    if system:
        wire["system"] = system
    if payload.get("tools"):
        wire["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})} for t in payload["tools"]]
        choice = payload.get("tool_choice", "auto")
        wire["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]} if isinstance(choice, dict) else {"type": "auto" if choice == "auto" else "any"}
    return wire


def project(payload, snapshot, replay):
    """Use native data only inside an exact prefix/model/connection boundary."""
    protocol = kind(snapshot)
    current = scope(snapshot, payload)
    sources = payload.get("messages", [])
    entries = (replay or {}).get("entries", {})
    def text_only(item):
        item = public_message(item)
        calls = item.pop("tool_calls", None)
        item.pop("tool_call_id", None)
        if item.get("role") == "assistant":
            content = item.get("content", "")
            if isinstance(content, list):
                content = "\n".join(str(part.get("text", "")) for part in content
                                    if isinstance(part, dict) and part.get("type") == "text")
            if calls and not content:
                content = "[Prior assistant tool work]"
            item["role"] = "user"
            item["content"] = "[Prior assistant message]\n" + str(content)
        if item.get("role") == "tool":
            item["role"] = "user"
            item["content"] = "[Prior tool result]\n" + str(item.get("content", ""))
        return item
    result = []
    broken_tool_group = False
    for msg in sources:
        item = public_message(msg)
        if item.get("role") == "assistant":
            entry = entries.get(msg.get("_protocolRef"))
            valid = (protocol and entry and entry["scope"] == current
                     and entry["message"] == item and entry["history"] == digest(result))
            broken_tool_group = not valid
            if not valid:
                result = [text_only(m) for m in result]
                item = text_only(item)
            else:
                validate_native(protocol, entry["native"], item)
                if protocol == "deepseek":
                    item.update(copy.deepcopy(entry["native"]))
                else:
                    item["_nativeBlocks"] = copy.deepcopy(entry["native"])
        elif item.get("role") == "tool" and broken_tool_group:
            item = text_only(item)
        result.append(item)
    payload = copy.deepcopy(payload)
    payload["messages"] = result
    if protocol == "deepseek" and any(m.get("role") == "assistant" and "reasoning_content" not in m for m in result):
        fail()
    return payload, current
