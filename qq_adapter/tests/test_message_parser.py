from __future__ import annotations

import unittest

from qq_adapter.services.message_parser import extract_text_from_message_content, parse_command


class MessageParserTestCase(unittest.TestCase):
    def test_extract_plain_text(self) -> None:
        self.assertEqual(extract_text_from_message_content(" 你好 "), "你好")

    def test_extract_json_text(self) -> None:
        self.assertEqual(extract_text_from_message_content('{"text":" 帮我看下 "}') , "帮我看下")

    def test_parse_help(self) -> None:
        parsed = parse_command("帮助")
        self.assertEqual(parsed.command, "help")

    def test_parse_analysis(self) -> None:
        parsed = parse_command("深度分析 某热点")
        self.assertEqual(parsed.command, "analysis")
        self.assertEqual(parsed.text, "某热点")

    def test_parse_report(self) -> None:
        parsed = parse_command("生成报告")
        self.assertEqual(parsed.command, "report")


if __name__ == "__main__":
    unittest.main()
