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
            self.task_service.update_task_status(task_id, "failed", current_step="小说不存在")
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
                self.task_service.update_task_status(task_id, "failed", current_step=step_name)
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
        """执行生成下一章任务（真实步骤拆分版）"""
        task = self.db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
        if not task:
            return
        
        self.task_service.update_task_status(task_id, "running", current_step="开始生成章节")
        
        chapter_service = ChapterService(self.db)
        
        steps = [
            ("生成章节细纲", "main"),
            ("生成章节正文", "main"),
            ("质检评分", "checker"),
            ("重写优化", "main"),
            ("润色正文", "editor"),
            ("提取记忆", "memory"),
            ("导出章节", "main"),
        ]
        
        total_steps = len(steps)
        self.task_service.update_task_status(task_id, "running", total_steps=total_steps, progress=0)
        
        chapter = None
        chapter_no = None
        
        try:
            for i, (step_name, role) in enumerate(steps):
                step = self.task_service.add_step(task_id, task.novel_id, step_name, i, role)
                self.task_service.update_step(step.id, "running")
                
                if step_name == "生成章节细纲":
                    outline_result = chapter_service.generate_outline(task.novel_id)
                    chapter_no = outline_result["chapter_no"]
                    
                    # 创建章节记录
                    from app.models import Chapter
                    chapter = Chapter(
                        novel_id=task.novel_id,
                        chapter_no=chapter_no,
                        outline=outline_result.get("outline", ""),
                        status="outline_done"
                    )
                    self.db.add(chapter)
                    self.db.commit()
                    self.db.refresh(chapter)
                    
                    self.task_service.update_step(
                        step.id, "success",
                        input_prompt=outline_result.get("prompt", ""),
                        raw_output=outline_result.get("raw_output", ""),
                        parsed_output=outline_result.get("outline", "")[:1500],
                        provider_role=role,
                        model_name=outline_result.get("model", "")
                    )
                
                elif step_name == "生成章节正文":
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
                
                elif step_name == "质检评分":
                    if chapter:
                        review_result = chapter_service.review_draft(chapter.id)
                        self.task_service.update_step(
                            step.id, "success",
                            input_prompt=f"质检章节 {chapter_no}",
                            raw_output=str(review_result.get("review", {})),
                            parsed_output=review_result.get("parsed_output", ""),
                            provider_role=role
                        )
                
                elif step_name == "重写优化":
                    if chapter:
                        # 简化处理：如果有 review 结果则重写
                        rewrite_result = chapter_service.rewrite_if_needed(chapter.id, {})
                        if rewrite_result.get("rewritten_text"):
                            chapter.final_text = rewrite_result["rewritten_text"]
                            self.db.commit()
                        
                        self.task_service.update_step(
                            step.id, "success",
                            parsed_output=rewrite_result.get("parsed_output", "重写完成")
                        )
                
                elif step_name == "润色正文":
                    if chapter:
                        polish_result = chapter_service.polish_text(chapter.id)
                        if not polish_result.get("skipped"):
                            chapter.final_text = polish_result.get("polished_text", chapter.final_text)
                            chapter.status = "polished"
                            self.db.commit()
                        
                        self.task_service.update_step(
                            step.id, "success",
                            parsed_output=polish_result.get("parsed_output", "润色完成")
                        )
                
                elif step_name == "提取记忆":
                    mem_result = chapter_service.extract_memory(chapter.id if chapter else None)
                    self.task_service.update_step(
                        step.id, "success",
                        parsed_output=mem_result.get("parsed_output", "记忆提取完成")
                    )
                
                elif step_name == "导出章节":
                    if chapter:
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
            self.task_service.update_task_status(task_id, "failed", current_step=str(e))

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
                self.task_service.update_task_status(task_id, "failed", current_step=f"第 {current} 章失败: {str(e)}")
                return
        
        self.task_service.update_task_status(task_id, "success", current_step=f"已完成连续生成 {chapter_count} 章", progress=100)
