from sqlalchemy.orm import Session
from app.services.task_service import TaskService
from app.services.llm_service import LLMService
from app.services.bible_service import BibleService
from app.services.chapter_service import ChapterService
from app.models import GenerationTask
import time

class AgentRunner:
    def __init__(self, db: Session):
        self.db = db
        self.task_service = TaskService(db)
        self.llm = LLMService(db)

    @staticmethod
    def _review_passed(review_result: dict, min_score: int) -> bool:
        """兼容质检结果的外层/内层结构，避免通过后仍重复重写。"""
        review_result = review_result or {}
        nested = review_result.get("review") if isinstance(review_result.get("review"), dict) else {}
        score = review_result.get("score", nested.get("score", 0))
        passed = review_result.get("pass", nested.get("pass", False))
        if isinstance(passed, str):
            passed = passed.lower() in {"true", "1", "yes", "pass", "passed", "通过"}
        try:
            score = int(score or 0)
        except (TypeError, ValueError):
            score = 0
        return bool(passed) and score >= min_score

    def _upsert_working_chapter(self, novel_id: int, chapter_no: int, title: str, outline: str):
        from app.models import Chapter
        chapter = self.db.query(Chapter).filter(
            Chapter.novel_id == novel_id,
            Chapter.chapter_no == chapter_no,
        ).first()
        if chapter and chapter.status == "final":
            raise ValueError(f"第 {chapter_no} 章已经定稿，不能覆盖")
        if not chapter:
            chapter = Chapter(novel_id=novel_id, chapter_no=chapter_no)
            self.db.add(chapter)
        chapter.title = title
        chapter.outline = outline
        chapter.draft_text = None
        chapter.final_text = None
        chapter.word_count = 0
        chapter.quality_score = 0
        chapter.status = "outline_done"
        self.db.commit()
        self.db.refresh(chapter)
        return chapter

    def run_generate_bible(self, task_id: int):
        """执行生成 Bible 任务"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step="生成小说 Bible")
        
        steps = [
            ("生成核心卖点", "main"),
            ("生成世界观设定", "main"),
            ("生成主要情节", "main"),
            ("生成人物设定", "main"),
            ("生成力量体系", "main"),
            ("生成关系设定", "main"),
            ("生成文风指南", "main"),
            ("生成禁忌规则", "main"),
        ]
        
        total_steps = len(steps)
        self.task_service.update_task_status(task_id, "running", progress=0, total_steps=total_steps)
        
        # 真实 8 步骤 Bible 生成（每个步骤独立 LLM 调用）
        from app.models import Novel
        from app.utils import render_prompt
        
        novel = self.db.query(Novel).filter(Novel.id == task.novel_id).first()
        if not novel:
            self.task_service.update_task_status(
                task_id,
                "failed",
                current_step="小说不存在",
                error_message=f"Novel {task.novel_id} does not exist.",
            )
            return
        
        bible_sections = [
            ("生成核心卖点", "请只输出小说的核心卖点（爆点、独特看点、爽点），200-400字"),
            ("生成世界观设定", "请只输出世界观、背景、规则、势力，400-600字"),
            ("生成主要情节", "请只输出主线剧情大纲（起承转合），300-500字"),
            ("生成人物设定", "请只输出主要人物（姓名、性格、动机、关系），300-500字"),
            ("生成力量体系", "请只输出力量/能力/修炼体系设定，200-400字"),
            ("生成关系设定", "请只输出人物间核心关系网，200-400字"),
            ("生成文风指南", "请只输出写作风格、叙事手法、语言特点，150-300字"),
            ("生成禁忌规则", "请只输出内容禁忌、审核规则、必须遵守的限制，100-200字"),
        ]
        
        total_steps = len(bible_sections)
        self.task_service.update_task_status(task_id, "running", progress=0, total_steps=total_steps)
        
        full_bible_parts = []
        
        for i, (step_name, instruction) in enumerate(bible_sections):
            step = self.task_service.add_step(task_id, task.novel_id, step_name, i, "main")
            self.task_service.update_step(step.id, "running")
            
            # 先构建 prompt（无论成功失败都要记录）
            base_prompt = render_prompt("novel_bible.md", {
                "title": novel.title,
                "genre": novel.genre,
                "style": novel.style,
                "description": novel.description or "",
                "target_words": novel.target_words,
                "chapter_words": novel.chapter_words,
            })
            full_prompt = f"{base_prompt}\n\n【本步骤要求】\n{instruction}\n\n请严格按照本步骤要求输出，不要输出其他部分。"
            
            try:
                trace = self.llm.generate_with_trace(full_prompt, provider="main")
                
                content = trace.get("content", "")
                full_bible_parts.append(f"## {step_name}\n{content}")
                
                self.task_service.update_step(
                    step.id, "success",
                    input_prompt=full_prompt,
                    raw_output=trace.get("raw_response", ""),
                    parsed_output=content,
                    provider_role="main",
                    model_name=trace.get("model", "")
                )
                
            except Exception as e:
                import traceback
                error_detail = f"{str(e)}\n{traceback.format_exc()}"
                # 失败时也要把 prompt 写进去
                self.task_service.update_step(
                    step.id, "failed",
                    input_prompt=full_prompt,
                    error_message=error_detail,
                    provider_role="main"
                )
                self.task_service.update_task_status(
                    task_id,
                    "failed",
                    current_step=step_name,
                    error_message=error_detail,
                )
                return
            
            progress = int((i + 1) / total_steps * 100)
            self.task_service.update_task_status(task_id, "running", progress=progress, current_step=step_name)
        
        # 合并保存完整 Bible
        from app.services.bible_service import BibleService
        bible_service = BibleService(self.db)
        full_text = "\n\n".join(full_bible_parts)
        
        # 直接写入数据库
        from app.models import NovelBible
        existing = self.db.query(NovelBible).filter(NovelBible.novel_id == task.novel_id).first()
        if existing:
            existing.full_text = full_text
        else:
            new_bible = NovelBible(novel_id=task.novel_id, full_text=full_text)
            self.db.add(new_bible)
        self.db.commit()
        
        self.task_service.update_task_status(task_id, "success", current_step="Bible 生成完成", progress=100)

    def run_generate_chapter(self, task_id: int):
        """执行生成下一章任务（章节生产线版）"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        chapter_service = ChapterService(self.db)
        steps = [
            ("章节生产卡：目标 / POV / 伏笔", "main"),
            ("初稿写作", "main"),
            ("审核：连续性 / POV / 伏笔", "checker"),
            ("修订重写", "main"),
            ("润色定稿", "editor"),
            ("记忆隔离与伏笔台账", "memory"),
            ("正文入库与导出", "main"),
        ]
        total_steps = len(steps)
        self.task_service.update_task_status(task_id, "running", current_step="开始章节生产线", total_steps=total_steps, progress=0)
        
        chapter = None
        chapter_no = None
        review_result = {}
        
        try:
            for i, (step_name, role) in enumerate(steps):
                self.task_service.update_task_status(
                    task_id,
                    "running",
                    progress=int(i / total_steps * 100),
                    current_step=step_name,
                )
                step = self.task_service.add_step(task_id, task.novel_id, step_name, i, role)
                self.task_service.update_step(step.id, "running")
                
                if step_name.startswith("章节生产卡"):
                    outline_result = chapter_service.generate_outline(task.novel_id)
                    chapter_no = outline_result["chapter_no"]
                    
                    chapter = self._upsert_working_chapter(
                        task.novel_id,
                        chapter_no,
                        chapter_service._title_from_outline(outline_result.get("outline", ""), chapter_no),
                        outline_result.get("outline", ""),
                    )
                    
                    self.task_service.update_step(
                        step.id, "success",
                        input_prompt=outline_result.get("prompt", ""),
                        raw_output=outline_result.get("raw_output", ""),
                        parsed_output=outline_result.get("outline", "")[:1500],
                        provider_role=role,
                        model_name=outline_result.get("model", "")
                    )
                
                elif step_name == "初稿写作":
                    if chapter:
                        draft_result = chapter_service.generate_draft(task.novel_id, chapter_no, chapter.outline)
                        chapter.draft_text = draft_result.get("draft_text", "")
                        chapter.status = "draft_done"
                        self.db.commit()
                        
                        self.task_service.update_step(
                            step.id, "success",
                            input_prompt=draft_result.get("prompt", ""),
                            raw_output=draft_result.get("raw_output", ""),
                            parsed_output=draft_result.get("draft_text", "")[:1500],
                            provider_role=role,
                            model_name=draft_result.get("model", "")
                        )
                
                elif step_name.startswith("审核"):
                    if chapter:
                        review_result = chapter_service.review_draft(chapter.id)
                        self.task_service.update_step(
                            step.id, "success",
                            input_prompt=f"质检章节 {chapter_no}",
                            raw_output=str(review_result.get("review", {})),
                            parsed_output=review_result.get("parsed_output", ""),
                            provider_role=role
                        )
                
                elif step_name == "修订重写":
                    if chapter:
                        min_score = int(getattr(__import__("app.config", fromlist=["settings"]).settings, "writing", {}).get("min_quality_score", 75))
                        if self._review_passed(review_result, min_score):
                            chapter.final_text = chapter.draft_text
                            chapter.status = "review_passed"
                            self.db.commit()
                            rewrite_result = {"parsed_output": "审核通过，保留初稿进入润色。"}
                        else:
                            rewrite_result = chapter_service.rewrite_if_needed(chapter.id, review_result)
                            if rewrite_result.get("rewritten_text"):
                                chapter.final_text = rewrite_result["rewritten_text"]
                                chapter.status = "rewritten"
                                self.db.commit()
                        
                        self.task_service.update_step(
                            step.id, "success",
                            parsed_output=rewrite_result.get("parsed_output", "重写完成")
                        )
                
                elif step_name == "润色定稿":
                    if chapter:
                        if not chapter.final_text:
                            chapter.final_text = chapter.draft_text or ""
                        polish_result = chapter_service.polish_text(chapter.id)
                        if not polish_result.get("skipped"):
                            chapter.final_text = polish_result.get("polished_text", chapter.final_text)
                            chapter.status = "polished"
                        else:
                            chapter.status = "polished_skipped"
                        self.db.commit()
                        
                        self.task_service.update_step(
                            step.id, "success",
                            parsed_output=polish_result.get("parsed_output", "润色完成")
                        )
                
                elif step_name == "记忆隔离与伏笔台账":
                    mem_result = chapter_service.extract_memory(chapter.id if chapter else None)
                    self.task_service.update_step(
                        step.id, "success",
                            parsed_output=mem_result.get("parsed_output", "记忆提取完成")
                    )
                
                elif step_name == "正文入库与导出":
                    if chapter:
                        if not chapter.final_text:
                            chapter.final_text = chapter.draft_text or ""
                        chapter.word_count = len("".join(chapter.final_text.split()))
                        chapter.status = "final"
                        self.db.commit()
                        export_result = chapter_service.export_chapter(chapter.id)
                        self.task_service.update_step(
                            step.id, "success",
                            parsed_output=export_result.get("parsed_output", "导出完成")
                        )
                
                progress = int((i + 1) / total_steps * 100)
                self.task_service.update_task_status(task_id, "running", progress=progress, current_step=step_name)
            
            # 最终更新小说进度
            if chapter:
                from app.models import Novel
                novel = self.db.query(Novel).filter(Novel.id == task.novel_id).first()
                if novel:
                    novel.current_chapter_no = chapter.chapter_no
                    novel.total_words = (novel.total_words or 0) + (chapter.word_count or 0)
                    self.db.commit()
            
            self.task_service.update_task_status(task_id, "success", current_step="章节生成完成", progress=100)
            
        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            self.task_service.update_step(step.id if 'step' in locals() else 0, "failed", error_message=error_detail)
            self.task_service.update_task_status(task_id, "failed", current_step=str(e), error_message=error_detail)

    def run_full_pipeline(self, task_id: int):
        """从选题/Bible 到一章正文的完整生产线。"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return

        from app.models import Novel, NovelBible, Chapter
        from app.utils import render_prompt
        from app.services.memory_service import MemoryService

        novel = self.db.query(Novel).filter(Novel.id == task.novel_id).first()
        if not novel:
            self.task_service.update_task_status(task_id, "failed", current_step="小说不存在", error_message=f"Novel {task.novel_id} does not exist.")
            return

        chapter_service = ChapterService(self.db)
        memory_service = MemoryService(self.db)
        steps = [
            ("选题定位 / 读者承诺", "main"),
            ("设定 Bible / 总纲 / POV / 伏笔台账", "main"),
            ("章节生产卡：目标 / POV / 伏笔", "main"),
            ("初稿写作", "main"),
            ("审核：连续性 / POV / 伏笔", "checker"),
            ("修订重写", "main"),
            ("润色定稿", "editor"),
            ("记忆隔离与伏笔台账", "memory"),
            ("正文入库与导出", "main"),
        ]
        self.task_service.update_task_status(task_id, "running", current_step="启动完整生产线", total_steps=len(steps), progress=0)

        chapter = None
        chapter_no = None
        review_result = {}

        try:
            bible = self.db.query(NovelBible).filter(NovelBible.novel_id == task.novel_id).first()
            for i, (step_name, role) in enumerate(steps):
                self.task_service.update_task_status(
                    task_id,
                    "running",
                    current_step=step_name,
                    progress=int(i / len(steps) * 100),
                )
                step = self.task_service.add_step(task_id, task.novel_id, step_name, i, role)
                self.task_service.update_step(step.id, "running")

                if step_name.startswith("选题定位"):
                    if bible and bible.full_text:
                        parsed = "已存在 Bible，沿用其中的选题定位与读者承诺。"
                        self.task_service.update_step(step.id, "success", parsed_output=parsed, provider_role=role)
                    else:
                        prompt = render_prompt("novel_bible.md", {
                            "title": novel.title,
                            "genre": novel.genre,
                            "style": novel.style,
                            "description": novel.description or "",
                            "target_words": novel.target_words,
                            "chapter_words": novel.chapter_words,
                        })
                        trace = self.llm.generate_with_trace(prompt, provider="main")
                        bible = NovelBible(novel_id=task.novel_id, full_text=trace.get("content", ""))
                        self.db.add(bible)
                        self.db.commit()
                        memory_service.record_memory(task.novel_id, f"选题/Bible 已建立：{novel.title}", "production_contract", importance=9)
                        self.task_service.update_step(
                            step.id, "success",
                            input_prompt=prompt,
                            raw_output=trace.get("raw_response", ""),
                            parsed_output=(trace.get("content", "")[:1800]),
                            provider_role=role,
                            model_name=trace.get("model", ""),
                        )

                elif step_name.startswith("设定 Bible"):
                    bible = bible or self.db.query(NovelBible).filter(NovelBible.novel_id == task.novel_id).first()
                    parsed = bible.full_text if bible else ""
                    memory_service.record_memory(task.novel_id, "Bible 已锁定：角色 POV、伏笔台账、分卷大纲必须作为后续生成合同。", "bible_lock", importance=9)
                    self.task_service.update_step(step.id, "success", parsed_output=parsed[:2200], provider_role=role)

                elif step_name.startswith("章节生产卡"):
                    outline_result = chapter_service.generate_outline(task.novel_id)
                    chapter_no = outline_result["chapter_no"]
                    chapter = self._upsert_working_chapter(
                        task.novel_id,
                        chapter_no,
                        chapter_service._title_from_outline(outline_result.get("outline", ""), chapter_no),
                        outline_result.get("outline", ""),
                    )
                    self.task_service.update_step(
                        step.id, "success",
                        input_prompt=outline_result.get("prompt", ""),
                        raw_output=outline_result.get("raw_output", ""),
                        parsed_output=outline_result.get("outline", "")[:1800],
                        provider_role=role,
                        model_name=outline_result.get("model", ""),
                    )

                elif step_name == "初稿写作":
                    draft_result = chapter_service.generate_draft(task.novel_id, chapter_no, chapter.outline)
                    chapter.draft_text = draft_result.get("draft_text", "")
                    chapter.status = "draft_done"
                    self.db.commit()
                    self.task_service.update_step(
                        step.id, "success",
                        input_prompt=draft_result.get("prompt", ""),
                        raw_output=draft_result.get("raw_output", ""),
                        parsed_output=draft_result.get("draft_text", "")[:1800],
                        provider_role=role,
                        model_name=draft_result.get("model", ""),
                    )

                elif step_name.startswith("审核"):
                    review_result = chapter_service.review_draft(chapter.id)
                    self.task_service.update_step(
                        step.id, "success",
                        input_prompt=f"审核章节 {chapter_no}",
                        raw_output=str(review_result),
                        parsed_output=str(review_result),
                        provider_role=role,
                    )

                elif step_name == "修订重写":
                    min_score = int(getattr(__import__("app.config", fromlist=["settings"]).settings, "writing", {}).get("min_quality_score", 75))
                    if self._review_passed(review_result, min_score):
                        chapter.final_text = chapter.draft_text
                        chapter.status = "review_passed"
                        self.db.commit()
                        parsed = "审核通过，保留初稿进入润色。"
                    else:
                        rewrite_result = chapter_service.rewrite_if_needed(chapter.id, review_result)
                        chapter.final_text = rewrite_result.get("rewritten_text") or chapter.draft_text
                        chapter.status = "rewritten"
                        self.db.commit()
                        parsed = rewrite_result.get("parsed_output", "")
                    self.task_service.update_step(step.id, "success", parsed_output=parsed, provider_role=role)

                elif step_name == "润色定稿":
                    if not chapter.final_text:
                        chapter.final_text = chapter.draft_text or ""
                    polish_result = chapter_service.polish_text(chapter.id)
                    if not polish_result.get("skipped"):
                        chapter.final_text = polish_result.get("polished_text", chapter.final_text)
                    chapter.status = "polished"
                    self.db.commit()
                    self.task_service.update_step(step.id, "success", parsed_output=polish_result.get("parsed_output", "润色完成"), provider_role=role)

                elif step_name == "记忆隔离与伏笔台账":
                    mem_result = chapter_service.extract_memory(chapter.id)
                    self.task_service.update_step(step.id, "success", parsed_output=mem_result.get("parsed_output", "记忆提取完成"), provider_role=role)

                elif step_name == "正文入库与导出":
                    chapter.final_text = chapter.final_text or chapter.draft_text or ""
                    chapter.word_count = len("".join(chapter.final_text.split()))
                    chapter.status = "final"
                    self.db.commit()
                    export_result = chapter_service.export_chapter(chapter.id)
                    self.task_service.update_step(step.id, "success", parsed_output=export_result.get("parsed_output", "导出完成"), provider_role=role)

                progress = int((i + 1) / len(steps) * 100)
                self.task_service.update_task_status(task_id, "running", current_step=step_name, progress=progress)

            novel.current_chapter_no = chapter.chapter_no if chapter else novel.current_chapter_no
            novel.total_words = (novel.total_words or 0) + ((chapter.word_count or 0) if chapter else 0)
            novel.failed_times = 0
            self.db.commit()
            self.task_service.update_task_status(task_id, "success", current_step="完整生产线完成", progress=100)

        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            if 'step' in locals():
                self.task_service.update_step(step.id, "failed", error_message=error_detail, provider_role=role)
            self.task_service.update_task_status(task_id, "failed", current_step=str(e), error_message=error_detail)

    def run_continuous_generate(self, task_id: int, novel_id: int, chapter_count: int):
        """连续生成多章"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step=f"准备连续生成 {chapter_count} 章")
        
        chapter_service = ChapterService(self.db)
        
        for i in range(chapter_count):
            task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
            if task.status in ["paused", "cancelled"]:
                break
            
            current = i + 1
            self.task_service.update_task_status(
                task_id, 
                "running", 
                current_step=f"正在生成第 {current}/{chapter_count} 章"
            )
            
            try:
                chapter_service.generate_next_chapter(novel_id)
                progress = int((current / chapter_count) * 100)
                self.task_service.update_task_status(task_id, "running", progress=progress)
                
            except Exception as e:
                self.task_service.update_task_status(
                    task_id,
                    "failed",
                    current_step=f"第 {current} 章失败: {str(e)}",
                    error_message=str(e),
                )
                return
        
        self.task_service.update_task_status(task_id, "success", current_step=f"已完成连续生成 {chapter_count} 章", progress=100)
