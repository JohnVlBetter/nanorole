# Nanorole 下一阶段路线图

## 目标

Nanorole 下一阶段先做成本地工作台，而不是直接做线上产品、游戏 SDK 或完整剧本杀引擎。

核心方向是两条主线分阶段合流：

- 情感陪伴内核：把现有单角色长记忆聊天打磨成稳定、可观察、可评估的陪伴 runtime。
- 角色扮演与叙事内核：加入世界状态、剧情事件、线索/事实、多角色对话，为剧本杀和游戏 NPC 做底层准备。

语音情感陪伴先只预留消息、事件和数据接口，不在本阶段接入真实 STT/TTS。Graph RAG 和完整剧本杀规则延后。

## 当前状态

仓库当前已经具备单角色陪伴聊天 MVP：

- Python FastAPI runtime 负责核心聊天、会话、上下文、记忆和日志。
- TypeScript CLI/demo 负责本地命令行与浏览器工作台。
- 角色包使用 `examples/roles/<role>/character.yaml`。
- SQLite 本地持久化位于 `.nanorole/nanorole.sqlite3`。
- 已支持持久会话、消息、长期记忆、关系状态、会话摘要、上下文预览和记忆管理页。
- 当前测试基线干净：Python runtime 51 个测试通过，TypeScript workspaces 21 个测试通过。

当前架构适合继续演进为本地工作台，但不适合马上同时引入多角色、剧本杀、语音、Graph RAG 和游戏 SDK。下一阶段应先把状态模型、消息模型和扩展点定稳。

## 产品原则

- 本地优先：先保证单机可用、可调试、可导出，不做登录、多租户或云同步。
- 记忆可控：陪伴记忆必须继续可查看、可编辑、可删除，不能成为隐藏状态。
- 剧情状态与陪伴记忆分离：用户长期偏好、关系状态属于 companion memory；世界事实、线索、隐藏信息属于 story state。
- 多角色先做编排，不做复杂智能体自治：第一版由 director/orchestrator 决定谁发言、发言目的和可见信息。
- 结构化状态先于 Graph RAG：先把事实、事件、线索、角色关系做成可调试的数据结构，再考虑图检索。
- 语音先做协议预留：消息可以携带 modality、emotion、audio reference，但工作台仍以文本为主。

## 阶段规划

### Phase 0: 地基加固

目标是避免后续扩表和接口演进时破坏现有 MVP。

关键工作：

- 增加 SQLite schema version 和 migration runner，替代只依赖 `create table if not exists` 的隐式升级。
- 给现有表结构写迁移回归测试，确保旧数据库可以升级。
- 固定当前单角色 companion 行为基线：会话创建、消息流式输出、记忆抽取、记忆删除、上下文预览必须保持兼容。
- 增加 context golden tests，防止后续多角色和剧情状态改坏现有 prompt 结构。
- 梳理本地工作台文案和角色示例文件编码显示问题，确保中文角色包在浏览器和日志中可读。

完成标准：

- 旧的 `POST /v1/sessions { role_id }` 仍可用。
- 旧会话和旧记忆数据无需手工处理即可继续读取。
- Python 和 TypeScript 测试保持通过。

### Phase 1: Companion Kernel v2

目标是把现有陪伴聊天内核整理成可复用的 turn pipeline，为多角色和剧情模式复用。

关键工作：

- 抽出统一对话回合流程：输入持久化、上下文组装、模型调用、输出持久化、记忆抽取、摘要更新、事件记录。
- 消息模型预留字段：`speakerId`、`inputModality`、`outputModality`、`emotionLabel`、`audioRef`。
- 记忆抽取继续非阻塞，失败不能影响用户聊天。
- 增强陪伴质量 fixtures：不要记住、纠错、边界、敏感信息不写入、关系状态不过度亲密。
- 在工作台里把 context preview、memory inspector、logs 组织成更像调试工具的体验。

完成标准：

- 单角色长记忆陪伴聊天体验不退化。
- 每个回合的输入、输出、记忆、摘要、上下文选择都有可追踪事件。
- 语音相关字段存在但不要求 UI 或供应商实现。

### Phase 2: Scenario Package

目标是引入世界和剧情包，让角色扮演、剧本杀、游戏 NPC 共享同一套叙事基础。

建议新增 `examples/scenarios/<scenario>/scenario.yaml`，第一版包含：

- `id`、`name`、`version`、`description`
- `mode`: `roleplay` 或 `mystery`
- `roles`: 参与角色 id 列表
- `world`: 世界设定摘要
- `initial_scene`: 开场场景
- `initial_state`: 初始剧情状态
- `public_facts`: 开局公开事实
- `hidden_facts`: 调试可见、模型按可见性规则获取的隐藏事实
- `clues`: 可被揭示的线索

第一版不做复杂 DSL。YAML 只负责声明静态初始内容，运行时状态进入 SQLite。

完成标准：

- 工作台可以列出 scenario。
- 可以基于 scenario 创建会话。
- Scenario session 能加载多个角色、世界设定和初始剧情状态。

### Phase 3: Story State Engine

目标是让剧情状态可持久化、可查看、可影响上下文。

建议新增持久层概念：

- `story_states`: 每个 scenario session 的当前状态摘要。
- `scene_events`: 用户动作、角色发言、线索揭示、状态变化等事件。
- `story_facts`: 世界事实、人物关系、已知信息、隐藏信息。
- `clues`: 线索内容、可见性、揭示状态、来源事件。

建议新增 runtime API：

- `GET /v1/scenarios`
- `GET /v1/scenarios/{scenarioId}`
- `POST /v1/sessions` 支持 `mode`、`scenarioId`、`roleIds`
- `GET /v1/sessions/{sessionId}/story-state`
- `POST /v1/sessions/{sessionId}/events`

上下文组装规则：

- Companion memory 只提供用户长期偏好、边界、关系状态。
- Story state 提供当前场景、公开事实、已揭示线索、当前角色可见信息。
- Hidden facts 只能按可见性规则进入指定角色或 director 的上下文，不能直接暴露给普通角色回复。

完成标准：

- 剧情状态能随着事件变化。
- Context preview 能显示本轮用了哪些记忆、事实、线索和事件。
- 隐藏事实不会错误进入普通角色可见上下文。

### Phase 4: Multi-Role Sessions

目标是支持多个角色同场对话，但先保持调度简单。

关键工作：

- 增加 `session_participants`，保存 session 内角色、显示名、状态和可见性。
- 消息按 `speakerId` 归属角色；用户消息的 `speakerId` 可为空或为 `user`。
- 增加 director/orchestrator：每轮先判断哪些角色应该回应、每个角色的发言目标、可见信息范围。
- 第一版每轮最多让 1-2 个角色回应，避免对话发散。
- 如果 director JSON 输出失败，降级为主角色单回复，聊天不中断。

完成标准：

- 一个 scenario session 可以包含多个角色。
- 工作台能区分不同角色发言。
- 多角色回复不会污染彼此隐藏知识。
- 单角色 companion session 不受影响。

### Phase 5: 本地工作台升级

目标是让本地 demo 变成可用的创作与调试工作台。

关键工作：

- Chat 页面支持 companion session 与 scenario session。
- Sidebar 显示角色、场景、历史会话。
- 增加 Story Inspector：剧情状态、事件流、事实、线索、参与角色。
- Memory Inspector 继续只管理 companion memory。
- Context Preview 合并展示 system prompt、长期记忆、剧情事实、线索、最近事件。
- Logs 页面继续保留原始 JSONL，但优先展示请求、响应、director 决策、记忆抽取、剧情事件。

完成标准：

- 非开发者也能通过本地页面创建角色/场景会话并观察状态变化。
- 开发者能定位一次回复为什么用了某条记忆或线索。

### Phase 6: 剧本杀预备能力

目标不是完整剧本杀游戏，而是完成剧本杀所需的底层能力。

关键工作：

- 线索可被揭示、归档、标记为已读。
- 角色可以拥有私有知识和动机。
- Director 可以基于当前阶段限制角色能说什么。
- 支持剧情阶段：开场、自由探索、搜证、讨论、总结。
- 支持结局判定的最小事件接口，但不实现完整投票和胜负规则。

完成标准：

- 可以做一个小型 mystery scenario：多角色、隐藏事实、线索揭示、阶段推进。
- 仍然不需要 Graph RAG。

## 接口与数据模型方向

### Session Create

保留旧接口兼容：

```json
{
  "role_id": "clockwork-sage"
}
```

新增推荐形态：

```json
{
  "mode": "scenario",
  "scenarioId": "forgotten-observatory",
  "roleIds": ["clockwork-sage", "archive-keeper"]
}
```

### Message

现有字段继续保留：

```json
{
  "messageId": "...",
  "role": "assistant",
  "content": "..."
}
```

新增可选字段：

```json
{
  "speakerId": "clockwork-sage",
  "inputModality": "text",
  "outputModality": "text",
  "emotionLabel": "calm",
  "audioRef": null
}
```

### State Separation

三类状态必须分开：

- Session state：会话、消息、参与者、事件。
- Companion memory：用户偏好、边界、长期关系、稳定事实。
- Story state：世界事实、线索、隐藏知识、剧情阶段、角色私有信息。

这条边界是后续支持情感陪伴、角色扮演、剧本杀和游戏 NPC 的关键。

## 暂缓范围

本阶段明确不做：

- 真实 STT/TTS 供应商接入。
- 多用户账号、权限、云同步。
- Unity/Unreal SDK。
- Graph RAG、向量数据库、知识图谱。
- 完整剧本杀投票、计分、胜负闭环。
- 前端框架迁移。
- LangChain、LlamaIndex 等重型编排框架。

这些不是否定方向，而是等本地状态模型和工作台稳定后再接。

## 测试计划

Python runtime：

- 数据库迁移幂等。
- 旧数据升级后可读。
- 单角色 session API 兼容。
- Scenario package 加载校验。
- Story state 持久化与事件追加。
- Hidden facts 不进入普通角色上下文。
- 多角色消息按 `speakerId` 持久化和读取。
- Director 失败时降级为单角色回复。

TypeScript demo：

- 新增 scenario API proxy。
- Chat 页面仍能打开旧 companion session。
- Scenario session 能展示多角色消息。
- Story Inspector 能读取剧情状态、事件、线索。
- Context Preview 能展示记忆、事实和线索来源。

质量回归：

- 用户说“不要记住”时不写长期记忆。
- 用户删除记忆后上下文不再使用。
- 角色不能泄露隐藏事实。
- 多角色不会凭空知道别人的私有信息。
- 敏感信息不被静默写入长期记忆。

## 推荐下一步

下一份可执行计划应只覆盖 Phase 0 和 Phase 1：

- SQLite migration runner。
- 现有 companion 行为 golden tests。
- 统一 turn pipeline。
- 消息模型预留 modality/emotion/audio 字段。
- 工作台调试体验的小幅整理。

这样可以在不引入多角色复杂度的前提下，把后续扩展需要的地基先打稳。
