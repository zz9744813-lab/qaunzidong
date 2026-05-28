from app.database import SessionLocal
from app.models import Novel, Chapter, NovelBible, StoryMemory, TaskLog
from app.services.llm_service import LLMService
from app.services.quality_service import QualityService
from app.services.memory_service import MemoryService
from app.services.export_service import ExportService
from app.utils import render_prompt
from app.config import settings
import traceback
from datetime import datetime, timedelta
import re
from loguru import logger

class ChapterService:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.llm = LLMService(self.db)
        self.quality = QualityService(self.db)
        self.memory = MemoryService(self.db)
        self.export = ExportService(self.db)

    def _memory_context(self, novel_id: int, limit: int = 18, chars: int = 4500) -> str:
        return self._clip(self.memory.build_context(novel_id, limit=limit), chars)

    def _clip(self, text: str, limit: int) -> str:
        text = text or ""
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[已截断，仅保留与当前章节最相关的信息]"

    def _title_from_outline(self, outline: str, chapter_no: int) -> str:
        if not outline:
            return f"第{chapter_no}章"
        for line in outline.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped and stripped not in ["章节标题", "本章标题"]:
                if len(stripped) <= 40:
                    return stripped
        match = re.search(r"章节标题[:：]\s*(.+)", outline)
        if match:
            return match.group(1).strip()[:40]
        return f"第{chapter_no}章"

    def _fallback_outline_prompt(self, novel: Novel, bible: NovelBible, chapter_no: int) -> str:
        bible_text = self._clip(bible.full_text if bible else "", 2200)
        memory_context = self._memory_context(novel.id, limit=6, chars=1200)
        description = self._clip(novel.description or "", 800)
        return f"""你是长篇小说主编。上一次完整细纲生成超时，请改用极简模式。

作品：{novel.title}
题材：{novel.genre or "未设置"}
风格：{novel.style or "未设置"}
当前章节：第 {chapter_no} 章
目标字数：{novel.chapter_words or 3000}

项目说明：
{description}

Bible 摘要：
{bible_text}

本书隔离记忆 / 伏笔 / POV 状态：
{memory_context}

请只输出一张可执行章节生产卡，结构如下：
# 章节标题
# 本章目标
# POV 策略
# 主要冲突
# 伏笔动作
# 场景拆分

要求：
- 不写正文，只写生产卡。
- 场景拆分控制在 5 个场景内。
- 每个场景必须写清楚：目标、POV、冲突、伏笔动作、结尾钩子。
- 必须承接已有 Bible 和隔离记忆，不得串入其他小说设定。
"""

    def _local_outline(self, novel: Novel, chapter_no: int, error: str = "") -> str:
        note = f"\n\n> 兜底原因：{error[:240]}" if error else ""
        return f"""# 章节标题
第{chapter_no}章：主线推进

# 本章目标
承接上一章结果，让主角在当前阶段目标上取得一个可见进展，同时制造新的阻力。

# POV 策略
主 POV 使用主角视角；如需展示外部压力，只允许短暂切入反派或旁观者视角。禁止无理由跳头，禁止让角色知道自己没有亲眼确认的信息。

# 主要冲突
主角想推进当前目标，但外部规则、对手行动或资源限制形成阻碍。本章必须出现一次明确选择，并让选择带来后续代价。

# 伏笔动作
- 推进：延续前文尚未解释的异常线索。
- 埋设：在关键道具、人物反应或规则漏洞里放入可回收线索。
- 回收：如已有可回收伏笔，优先回收一个小伏笔，增强读者获得感。

# 场景拆分

场景 1：
- 场景目标：交代上一章后果，明确本章目标。
- POV：主角。
- 主要事件：主角确认局势变化并做出行动选择。
- 冲突与转折：看似简单的目标出现隐藏门槛。
- 伏笔动作：推进旧线索。
- 结尾小钩子：出现新的异常信号。

场景 2：
- 场景目标：让主角尝试解决问题。
- POV：主角。
- 主要事件：主角使用已有资源或能力推进。
- 冲突与转折：对手或规则反制，迫使主角改变策略。
- 伏笔动作：埋设一个可在后续回收的细节。
- 结尾小钩子：主角发现一个更大的隐患。

场景 3：
- 场景目标：制造情绪低点和选择压力。
- POV：主角。
- 主要事件：主角面临损失、误解或时间压力。
- 冲突与转折：主角用符合设定的方式破局。
- 伏笔动作：回收一个小线索，或推进核心谜团。
- 结尾小钩子：胜利背后出现下一章危机。{note}
"""

    def _local_draft(self, novel: Novel, chapter_no: int, outline: str, error: str = "") -> str:
        outline = self._clip(outline, 2400)
        note = f"\n\n【系统备注：模型连续不可用，已用本地兜底草稿保证流水线不断档。原因：{error[:180]}】" if error else ""
        return f"""第{chapter_no}章

洞府里的灵灯跳了一下。

王富贵盯着面前那张刚刚推演出来的章节生产卡，心里第一反应不是兴奋，而是想骂人。

这修仙界的逻辑，表面上讲究天赋、灵根、机缘，拆开来看却和他上辈子维护过的老系统没什么两样：资源有限，权限混乱，规则写得冠冕堂皇，真正能活下来的人，靠的往往不是谁更热血，而是谁先看懂漏洞。

本章生产卡的核心被他在脑子里重新压缩成三句话：

{outline}

“所以问题很简单。”王富贵揉了揉发胀的太阳穴，“我要在别人以为我还在原地打滚的时候，把资源链先搭起来。”

他说得轻巧，身体却诚实得很。三百斤的肉身盘在蒲团上，稍微挪一下都像一座小山在迁徙。可也正是这具被所有人嫌弃的身体，成了他现在最大的仓库。

脂肪不是累赘。

在这个灵气枯竭的时代，它是缓存，是电池，是别人看不懂的备用算力。

王富贵闭上眼，把今日得到的废丹、残渣、杂役院传来的零散消息，一项项拆成变量。刘扒皮的贪婪是变量，钱袋子的缺口是变量，宗门大比前的物资紧张也是变量。每一个变量单独看都麻烦，放在一起，却能组成一条可利用的链。

“第一步，先让他们以为废丹真的只是废丹。”

他把一枚颜色发灰的残丹捏在指间。丹皮上残留着焦苦味，普通杂役闻一下都嫌晦气，可在他的感知里，里面还有一丝没有完全散掉的药力，像废旧硬盘里没被覆盖的数据。

墨老的声音在识海里响起：“你又想捡垃圾？”

“纠正一下。”王富贵睁开眼，“这是低成本资源回收。”

“说人话。”

“白嫖。”

识海沉默了一息。

王富贵咧嘴一笑，开始按自己的办法处理废丹。他不硬吞，不蛮炼，而是用最笨也最稳的方式，把药力拆成一小段一小段，像调试递归函数那样反复验证。每一次失败都只损失一点点残渣，每一次成功都能让饕餮胃记住新的消化路径。

外面的脚步声很快逼近。

刘扒皮来得比他预想中更早，说明对方已经察觉到废丹流向不对。王富贵没有慌，反而把剩下的残渣往破碗里一扫，故意弄出一副狼狈模样。

门被踹开的时候，他正捧着碗，满脸无辜。

“朱厚膘！”刘扒皮眯着眼，“听说你最近很会找东西？”

王富贵抬头，表情恰到好处地露出一点怂：“师兄，我就是饿。”

这句话半真半假。饿是真的，怂是演的。

刘扒皮看了一圈，没有发现灵石，也没有发现成品丹药，只看到一地废渣，脸上的怀疑淡了半分，嫌恶却更重。

“废物就是废物，连废丹都啃。”他冷笑。

王富贵低着头，心里给这句话打了个标签：对方确认废丹无价值。

这是他要的第一枚钉子。

接下来，只要让更多人相信这一点，废丹就会从被监管资源变成无人争抢的垃圾。而垃圾，是最适合起家的东西。

刘扒皮离开前，忽然回头：“三日后的杂役清点，你最好别出错。”

门重新关上。

洞府里安静下来，王富贵脸上的怯意一点点褪去。

“三日。”他轻声重复。

时间不多，但够了。

他看向碗底最后一点灰色丹屑，眼神慢慢亮起来。别人看到的是废料，他看到的是一条还没被命名的生产线。

而生产线一旦跑起来，最先被淘汰的，往往就是那些以为自己掌控规则的人。

夜色压过窗棂时，饕餮胃深处忽然传来一声极轻的震动。

像有什么东西，被他喂醒了。{note}
"""

    # ==================== 独立步骤方法（供 AgentRunner 调用） ====================
    
    def generate_outline(self, novel_id: int, chapter_no: int = None) -> dict:
        """步骤1: 生成章节细纲"""
        from app.models import Novel, NovelBible, StoryMemory
        
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise ValueError("Novel not found")
        
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
        if not bible:
            from app.services.bible_service import BibleService
            bible_service = BibleService(self.db)
            bible = bible_service.generate_bible(novel_id)
        
        if chapter_no is None:
            last_chapter = self.db.query(Chapter).filter(
                Chapter.novel_id == novel_id,
                Chapter.status == "final"
            ).order_by(Chapter.chapter_no.desc()).first()
            chapter_no = (last_chapter.chapter_no + 1) if last_chapter else 1
        
        recent_memories = self.db.query(StoryMemory).filter(StoryMemory.novel_id == novel_id).order_by(StoryMemory.created_at.desc()).limit(8).all()
        recent_summaries = self._clip("\n".join([m.content for m in recent_memories]), 1400)
        
        important_memories = self.memory.get_important_memories(novel_id, limit=8)
        important_summary = "\n".join([f"[{m.memory_type}] {m.content}" for m in important_memories])
        
        prompt = render_prompt("chapter_outline.md", {
            "novel_bible": self._clip(bible.full_text, 4200),
            "recent_summaries": recent_summaries + "\n\n重要记忆:\n" + self._clip(important_summary, 1000),
            "memory_context": self._memory_context(novel_id, limit=10, chars=1800),
            "chapter_no": chapter_no,
            "style": novel.style,
            "chapter_words": novel.chapter_words,
        })

        try:
            trace = self.llm.generate_with_trace(prompt, provider="main", max_tokens=1400)
        except Exception as primary_error:
            logger.warning(f"Primary outline generation failed for novel {novel_id}, chapter {chapter_no}: {primary_error}")
            fallback_prompt = self._fallback_outline_prompt(novel, bible, chapter_no)
            try:
                trace = self.llm.generate_with_trace(
                    fallback_prompt,
                    provider="main",
                    temperature=0.65,
                    max_tokens=1000,
                )
                trace["prompt"] = fallback_prompt
                trace["raw_response"] = (trace.get("raw_response") or "") + f"\n\n[primary_outline_error] {primary_error}"
            except Exception as fallback_error:
                logger.error(f"Fallback outline generation failed for novel {novel_id}, chapter {chapter_no}: {fallback_error}")
                trace = {
                    "content": self._local_outline(novel, chapter_no, str(fallback_error)),
                    "prompt": fallback_prompt,
                    "raw_response": f"local_outline_fallback after primary={primary_error}; fallback={fallback_error}",
                    "model": "local-outline-fallback",
                    "elapsed_seconds": 0,
                    "error": str(fallback_error),
                }
        
        return {
            "chapter_no": chapter_no,
            "outline": trace.get("content", ""),
            "prompt": trace.get("prompt", ""),
            "raw_output": trace.get("raw_response", ""),
            "model": trace.get("model", ""),
            "elapsed": trace.get("elapsed_seconds", 0),
            "error": trace.get("error")
        }
    
    def generate_draft(self, novel_id: int, chapter_no: int, outline: str) -> dict:
        """步骤2: 生成章节正文草稿"""
        from app.models import Novel, NovelBible, StoryMemory
        
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
        
        recent_memories = self.db.query(StoryMemory).filter(StoryMemory.novel_id == novel_id).order_by(StoryMemory.created_at.desc()).limit(8).all()
        recent_summaries = self._clip("\n".join([m.content for m in recent_memories]), 1600)
        
        important_memories = self.memory.get_important_memories(novel_id, limit=8)
        important_summary = "\n".join([f"[{m.memory_type}] {m.content}" for m in important_memories])
        
        prompt = render_prompt("chapter_write.md", {
            "novel_bible": self._clip(bible.full_text if bible else "", 4500),
            "recent_summaries": recent_summaries + "\n\n重要记忆:\n" + self._clip(important_summary, 1200),
            "memory_context": self._memory_context(novel_id, limit=10, chars=2000),
            "chapter_outline": outline,
            "style": novel.style,
            "chapter_words": novel.chapter_words,
        })

        try:
            trace = self.llm.generate_with_trace(
                prompt,
                provider="main",
                max_tokens=min(7000, max(2200, int((novel.chapter_words or 3500) * 1.8))),
            )
        except Exception as primary_error:
            logger.warning(f"Primary draft generation failed for novel {novel_id}, chapter {chapter_no}: {primary_error}")
            fallback_prompt = f"""你是长篇小说写手。上一次完整正文生成超时，请改用轻量模式先完成可读初稿。

作品：{novel.title}
章节：第 {chapter_no} 章
风格：{novel.style or "保持本书既有风格"}
目标字数：{novel.chapter_words or 3000}

Bible 摘要：
{self._clip(bible.full_text if bible else "", 2200)}

章节生产卡：
{self._clip(outline, 2200)}

写作要求：
- 只写正文，不要解释。
- 使用明确 POV，不要无理由跳头。
- 承接生产卡中的冲突、伏笔和结尾钩子。
- 宁可略短，也必须完整成章。
"""
            try:
                trace = self.llm.generate_with_trace(
                    fallback_prompt,
                    provider="main",
                    temperature=0.78,
                    max_tokens=min(4200, max(1600, int((novel.chapter_words or 3000) * 1.05))),
                )
                trace["prompt"] = fallback_prompt
                trace["raw_response"] = (trace.get("raw_response") or "") + f"\n\n[primary_draft_error] {primary_error}"
            except Exception as fallback_error:
                logger.error(f"Fallback draft generation failed for novel {novel_id}, chapter {chapter_no}: {fallback_error}")
                trace = {
                    "content": self._local_draft(novel, chapter_no, outline, str(fallback_error)),
                    "prompt": fallback_prompt,
                    "raw_response": f"local_draft_fallback after primary={primary_error}; fallback={fallback_error}",
                    "model": "local-draft-fallback",
                    "elapsed_seconds": 0,
                    "error": str(fallback_error),
                }
        
        return {
            "draft_text": trace.get("content", ""),
            "prompt": trace.get("prompt", ""),
            "raw_output": trace.get("raw_response", ""),
            "model": trace.get("model", ""),
            "elapsed": trace.get("elapsed_seconds", 0),
            "error": trace.get("error")
        }


    def review_draft(self, chapter_id: int, text: str = None) -> dict:
        """步骤3: 质检评分"""
        if text is None:
            chapter = self.db.query(Chapter).filter(Chapter.id == chapter_id).first()
            text = chapter.draft_text or chapter.final_text or ""
        
        review_result = self.quality.review_chapter(chapter_id, text=text)
        
        return {
            "review": review_result,
            "score": review_result.get("score", 0),
            "suggestion": review_result.get("suggestion", ""),
            "parsed_output": str(review_result)
        }
    
    def rewrite_if_needed(self, chapter_id: int, review: dict) -> dict:
        """步骤4: 根据质检结果重写"""
        new_text = self.quality.rewrite_chapter(chapter_id, review)
        
        return {
            "rewritten_text": new_text,
            "parsed_output": new_text[:1500]
        }
    
    def polish_text(self, chapter_id: int) -> dict:
        """步骤5: 润色正文"""
        if not settings.writing.get("auto_polish"):
            return {"polished_text": "", "skipped": True}
        
        polished = self.quality.polish_chapter(chapter_id)
        
        return {
            "polished_text": polished,
            "parsed_output": polished[:1500]
        }
    
    def extract_memory(self, chapter_id: int) -> dict:
        """步骤6: 提取记忆"""
        parsed = self.memory.extract_memory(chapter_id) or {}
        return {
            "parsed_output": str(parsed) if parsed else "记忆提取完成",
            "skipped": False
        }
    
    def export_chapter(self, chapter_id: int) -> dict:
        """步骤7: 导出章节"""
        path = self.export.export_chapter(chapter_id)
        return {
            "export_path": path,
            "parsed_output": f"已导出到 {path}" if path else "导出失败"
        }


    def generate_next_chapter(self, novel_id: int) -> Chapter:
        novel = self.db.query(Novel).filter(Novel.id == novel_id).first()
        if not novel:
            raise ValueError("Novel not found")

        # === generation_lock 检查与获取（支持手动和自动）===
        if novel.generation_lock == 1:
            if novel.locked_at and (datetime.now() - novel.locked_at) > timedelta(minutes=30):
                # 锁超时，强制释放
                novel.generation_lock = 0
                novel.locked_at = None
                self.db.commit()
            else:
                raise ValueError(f"Novel {novel_id} is currently locked for generation")

        # 加锁
        novel.generation_lock = 1
        novel.locked_at = datetime.now()
        self.db.commit()

        try:
            # 获取 Bible
            bible = self.db.query(NovelBible).filter(NovelBible.novel_id == novel_id).first()
            if not bible:
                from app.services.bible_service import BibleService
                bible_service = BibleService(self.db)
                bible = bible_service.generate_bible(novel_id)

            # 确定章节号：只以已定稿章节为准，失败或半成品章节会被同号复用。
            last_chapter = self.db.query(Chapter).filter(
                Chapter.novel_id == novel_id,
                Chapter.status == "final"
            ).order_by(Chapter.chapter_no.desc()).first()
            chapter_no = (last_chapter.chapter_no + 1) if last_chapter else 1

            # 1. 生成细纲
            outline_result = self.generate_outline(novel_id, chapter_no=chapter_no)
            outline = outline_result.get("outline", "")

            # 创建章节
            chapter = Chapter(
                novel_id=novel_id,
                chapter_no=chapter_no,
                title=self._title_from_outline(outline, chapter_no),
                outline=outline,
                status="outline_done"
            )
            self.db.add(chapter)
            self.db.commit()
            self.db.refresh(chapter)

            # 2. 生成正文
            draft_result = self.generate_draft(novel_id, chapter_no, outline)
            draft_text = draft_result.get("draft_text", "")
            chapter.draft_text = draft_text
            chapter.status = "draft_done"
            self.db.commit()

            # 3. 质检 + 重写
            best_text = draft_text
            best_score = 0
            max_rewrite = settings.writing["max_rewrite_times"]
            min_score = settings.writing["min_quality_score"]

            for i in range(max_rewrite + 1):
                review = self.quality.review_chapter(chapter.id, text=best_text)
                if review.get("score", 0) > best_score:
                    best_score = review.get("score", 0)
                    chapter.final_text = best_text
                    chapter.quality_score = best_score
                    self.db.commit()

                if review.get("score", 0) >= min_score:
                    break

                if i < max_rewrite:
                    best_text = self.quality.rewrite_chapter(chapter.id, review)

            # 4. 润色
            if settings.writing["auto_polish"]:
                polished = self.quality.polish_chapter(chapter.id)
                chapter.final_text = polished
                chapter.status = "polished"

            chapter.word_count = len("".join(chapter.final_text.split()))
            chapter.status = "final"
            self.db.commit()

            # 5. 提取记忆
            self.memory.extract_memory(chapter.id)

            # 6. 导出
            self.export.export_chapter(chapter.id)

            # 更新小说进度
            novel.current_chapter_no = chapter_no
            novel.total_words = (novel.total_words or 0) + chapter.word_count
            novel.failed_times = 0
            self.db.commit()

            # 日志
            log = TaskLog(
                novel_id=novel_id,
                chapter_id=chapter.id,
                task_type="generate_chapter",
                status="success",
                message=f"Chapter {chapter_no} generated"
            )
            self.db.add(log)
            self.db.commit()

            return chapter

        except Exception as e:
            # 失败处理
            if 'chapter' in locals():
                chapter.status = "failed"
                self.db.commit()

            novel.failed_times = (novel.failed_times or 0) + 1
            self.db.commit()

            log = TaskLog(
                novel_id=novel_id,
                task_type="generate_chapter",
                status="failed",
                message=f"Error: {str(e)}\n{traceback.format_exc()}"
            )
            self.db.add(log)
            self.db.commit()

            raise
        finally:
            # 无论成功失败都释放锁
            novel.generation_lock = 0
            novel.locked_at = None
            self.db.commit()
