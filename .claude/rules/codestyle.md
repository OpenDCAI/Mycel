# 代码风格

**禁止**：monkeypatch、嵌套函数、单例/全局变量、metaclass/动态 import、eval/exec

**强制**：Pydantic 强类型校验输入输出；核心逻辑必须有日志；区分预期异常与系统错误，不吞异常
