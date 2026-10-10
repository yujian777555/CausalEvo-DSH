# Planner Phase 0 初始审阅

日期：2026-10-10
基线仓库 main：a9bef642e35eeed398f5578890a00f8872af2af0（仅 README.md）。
审阅结论：允许启动 Phase 0 基础设施开发与离线实验；live 缓存数据尚不存在。

已从官方 DeepSeek-Harness 源码/文档核对：
- Python SDK 可以通过 JSON-RPC 操作 Harness，RunResult 含 Session events；默认 SDK model 名可能与服务商展示名不同，必须验证实际 route。
- 官方适配器提供缓存用量桶；inputTokens 被定义为未缓存输入，与 cacheReadTokens/cacheWriteTokens 互斥。
- 上游 sdk-minimal 带持久 Shell，默认 permission 为 danger-full-access，不适合未经隔离的纯缓存 benchmark。
- Session 日志上传扩展可能默认启用，需要显式判断与配置。
- DeepSeek-Harness 为 Developer Preview，要求锁定确切上游版本，记录 breaking changes。

本轮风险排序：
P0：任何有效 Shell 权限暴露或 API Key 泄漏。
P0：忽略重试费用、误读互斥 Token 桶或虚构 live 数据。
P1：变更 System Prompt 与变化 Session 长度混为一谈。
P1：频繁变化的工具 schema 与不稳定前缀导致缓存对照失效。
P2：无法获得 provider 账单颗粒度时成本估算存在偏差。

当前待 Executor 交付：plan CE-DSH-P0-R1 中的全部条目。该审阅不是验收通过。
