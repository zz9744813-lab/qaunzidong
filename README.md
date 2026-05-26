# Novel Auto Factory

AI 自动小说工厂 - 第一版 MVP

## 功能

- 创建小说项目
- 配置多个 API (main, editor, checker)
- 自动生成小说设定
- 自动生成章节细纲、正文
- 自动质检、重写、润色
- 自动提取剧情记忆
- 自动保存和导出
- 自动循环生成
- Web 后台管理

## 安装

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

## 启动

访问地址将在终端日志中显示。

## 后续

详细需求见 AI_Novel_Auto_Factory_Dev_Spec.md

---

**注意**：本项目为第一版 MVP，优先保证核心链路可运行。