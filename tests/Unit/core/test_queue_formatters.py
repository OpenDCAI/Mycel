"""Tests for core/queue/formatters.py"""

import xml.etree.ElementTree as ET

from core.runtime.middleware.queue.formatters import format_chat_notification, format_command_notification


def _require_child(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(tag)
    assert child is not None
    return child


def _require_text(element: ET.Element) -> str:
    assert element.text is not None
    return element.text


class TestFormatChatNotification:
    def test_includes_explicit_read_messages_and_send_message_instructions(self):
        result = format_chat_notification(
            sender_name="alice",
            chat_id="chat-123",
            unread_count=2,
        )

        assert 'read_messages(chat_id="chat-123")' in result
        assert 'send_message(chat_id="chat-123", content="...")' in result
        assert "Prefer using this exact chat_id directly" in result
        assert "Do not treat your normal assistant text as a chat reply." in result


class TestFormatCommandNotification:
    """Test format_command_notification XML generation."""

    def test_basic_format(self):
        """Test basic XML structure."""
        result = format_command_notification(
            command_id="cmd-123",
            status="completed",
            exit_code=0,
            command_line="echo hello",
            output="hello\n",
        )

        # Should be valid XML
        root = ET.fromstring(result)
        assert root.tag == "system-reminder"

        # Check CommandNotification structure
        notif = root.find("CommandNotification")
        assert notif is not None
        assert _require_text(_require_child(notif, "CommandId")) == "cmd-123"
        assert _require_text(_require_child(notif, "Status")) == "completed"
        assert _require_text(_require_child(notif, "ExitCode")) == "0"
        assert _require_text(_require_child(notif, "CommandLine")) == "echo hello"
        assert _require_text(_require_child(notif, "Output")) == "hello\n"

    def test_failed_status(self):
        """Test failed command notification."""
        result = format_command_notification(
            command_id="cmd-456",
            status="failed",
            exit_code=1,
            command_line="false",
            output="",
        )

        root = ET.fromstring(result)
        notif = _require_child(root, "CommandNotification")
        assert _require_text(_require_child(notif, "Status")) == "failed"
        assert _require_text(_require_child(notif, "ExitCode")) == "1"

    def test_output_truncation(self):
        """Test output is truncated to 1000 characters."""
        long_output = "x" * 2000
        result = format_command_notification(
            command_id="cmd-789",
            status="completed",
            exit_code=0,
            command_line="cat large.txt",
            output=long_output,
        )

        root = ET.fromstring(result)
        notif = _require_child(root, "CommandNotification")
        output_text = _require_text(_require_child(notif, "Output"))
        assert len(output_text) == 1000
        assert output_text == "x" * 1000

    def test_empty_output(self):
        """Test empty output is handled correctly."""
        result = format_command_notification(
            command_id="cmd-empty",
            status="completed",
            exit_code=0,
            command_line="true",
            output="",
        )

        root = ET.fromstring(result)
        notif = _require_child(root, "CommandNotification")
        output_elem = _require_child(notif, "Output")
        assert output_elem.text is None or output_elem.text == ""

    def test_xml_special_characters_escaped(self):
        """Test XML special characters are properly escaped."""
        result = format_command_notification(
            command_id="cmd-special",
            status="completed",
            exit_code=0,
            command_line='echo "<tag>" & echo "test"',
            output="<output>&</output>",
        )

        # Should parse without error
        root = ET.fromstring(result)
        notif = _require_child(root, "CommandNotification")

        # Check escaped content is preserved
        cmd_line = _require_text(_require_child(notif, "CommandLine"))
        assert "<tag>" in cmd_line
        assert "&" in cmd_line

        output = _require_text(_require_child(notif, "Output"))
        assert "<output>" in output
        assert "&" in output

    def test_multiline_output(self):
        """Test multiline output is preserved."""
        result = format_command_notification(
            command_id="cmd-multi",
            status="completed",
            exit_code=0,
            command_line="ls -la",
            output="line1\nline2\nline3\n",
        )

        root = ET.fromstring(result)
        notif = _require_child(root, "CommandNotification")
        output = _require_text(_require_child(notif, "Output"))
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output
