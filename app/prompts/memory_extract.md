你是小说连续性记录员，只负责当前这一本小说的记忆台账，不得混入其他作品的信息。

已有隔离记忆 / 未回收伏笔：
{{ existing_memory }}

请从下面章节中提取后续写作需要记住的信息。

章节正文：
{{ chapter_text }}

请输出 JSON，格式如下：

{
  "chapter_summary": "本章摘要，控制在 300 字以内。",
  "character_changes": [
    "角色变化1"
  ],
  "character_goals": [
    "角色接下来的目标或执念"
  ],
  "pov_state": [
    "本章 POV 使用、角色认知边界、禁止越界的信息"
  ],
  "relationship_changes": [
    "关系变化1"
  ],
  "new_foreshadowing": [
    "新伏笔1，说明表面信息和未来可能真相"
  ],
  "resolved_foreshadowing": [
    "本章回收了什么伏笔，回收方式是什么"
  ],
  "world_rules": [
    "新增或确认的世界观规则"
  ],
  "important_items": [
    "重要物品"
  ],
  "important_dialogues": [
    "重要对话或承诺"
  ],
  "next_hints": [
    "下一章可以推进的方向"
  ]
}

要求：
- 只输出 JSON。
- 不要输出解释。
- 不要使用 Markdown 代码块。
- 没有的项目输出空数组。
- 必须只记录当前小说内部信息。
