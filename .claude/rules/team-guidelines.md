# Agent Team 规范

- PM 只协调，不写码，必须 spawn 子成员执行
- **完成 = 跑通 + 测试通过**，基础设施类还要验证端口可达
- 先搭基础设施，再写业务代码
- 每个成员先读懂现有代码再动手，核心原则"包一层"复用 sandbox/ 和 middleware/，❌ 不重造
- 每个模块完成后立即 review，不攒到最后

**环境**：Docker 已装，Redis/RabbitMQ 用容器；`proxy_on` 开代理；Supabase MCP 可用（`~/.mcp.json`）
