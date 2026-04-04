"""Tests for core/queue/formatters.py"""

import xml.etree.ElementTree as ET

from core.runtime.middleware.queue.formatters import format_chat_notification, format_command_notification


class TestFormatChatNotification:
    def test_includes_explicit_chat_read_and_chat_send_instructions(self):
        result = format_chat_notification(
            sender_name="alice",
            chat_id="chat-123",
            unread_count=2,
        )

        assert 'chat_read(chat_id="chat-123")' in result
        assert 'chat_send(chat_id="chat-123", content="...")' in result
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
        assert notif.find("CommandId").text == "cmd-123"
        assert notif.find("Status").text == "completed"
        assert notif.find("ExitCode").text == "0"
        assert notif.find("CommandLine").text == "echo hello"
        assert notif.find("Output").text == "hello\n"

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
        notif = root.find("CommandNotification")
        assert notif.find("Status").text == "failed"
        assert notif.find("ExitCode").text == "1"

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
        notif = root.find("CommandNotification")
        output_text = notif.find("Output").text
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
        notif = root.find("CommandNotification")
        output_elem = notif.find("Output")
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
        notif = root.find("CommandNotification")

        # Check escaped content is preserved
        cmd_line = notif.find("CommandLine").text
        assert "<tag>" in cmd_line
        assert "&" in cmd_line

        output = notif.find("Output").text
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
        notif = root.find("CommandNotification")
        output = notif.find("Output").text
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output
