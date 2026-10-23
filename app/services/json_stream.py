import json


class JsonObjectStream:
    """增量提取完整 JSON 对象，无需等待换行或整段模型回复结束。"""

    def __init__(self):
        """初始化跨分块保留的缓冲区、括号层级及字符串转义状态。"""
        self.buffer = ""
        self.depth = 0
        self.in_string = False
        self.escaped = False

    def feed(self, text: str):
        """接收新文本块，遇到完整对象立即产出解析结果。

        忽略对象外的说明文字；字符串中的括号不参与层级计数。
        未完成的对象留待下一块补齐，格式错误的完整对象跳过。
        """
        for char in text:
            if not self.depth:
                if char != "{":
                    continue
                self.buffer = ""
            self.buffer += char
            if len(self.buffer) > 65536:
                raise ValueError("AI 返回内容过长，请重试")
            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif char == "\\":
                    self.escaped = True
                elif char == '"':
                    self.in_string = False
            elif char == '"':
                self.in_string = True
            elif char == "{":
                self.depth += 1
            elif char == "}":
                self.depth -= 1
                if not self.depth:
                    try:
                        yield json.loads(self.buffer)
                    except json.JSONDecodeError:
                        pass
                    self.buffer = ""
