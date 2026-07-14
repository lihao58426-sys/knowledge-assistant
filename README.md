# 个人知识库助手 (Knowledge Assistant)

> 基于 ChromaDB + DeepSeek 的 RAG 知识库问答系统。扫描所有项目源码和技术文档，构建向量索引，通过自然语言获取基于真实代码的回答。

## 快速开始

```bash
pip install -r requirements.txt
# 1. 构建索引（首次使用）
python index.py
# 2. 启动服务
python server.py
# 3. 打开 http://localhost:8002
```

## 三种模式

| 模式 | 做什么 | 适用场景 |
|------|------|---------|
| 🔍 搜索 | ChromaDB 检索 + DeepSeek 回答，带来源引用 | 问技术问题、查实现方式 |
| 🎓 导师 | 勾选文件全文发 DeepSeek 逐模块讲解 | 学新项目、理解架构 |
| 📖 阅读 | 预生成结构化讲解，左右代码联动，笔记系统 | 精读代码、逐行分析 |

## 技术栈

| 层面 | 技术 |
|------|------|
| 向量库 | ChromaDB + text2vec-base-chinese |
| 问答 | DeepSeek Chat API |
| 后端 | FastAPI + Jinja2 |
| 前端 | Vanilla JS + ECharts 力导向图 + localStorage |
| 讲解 | DeepSeek 预生成 JSON，离线即时读取 |

## 项目结构

```
knowledge-assistant/
├── server.py              # FastAPI Web 服务
├── rag_engine.py          # RAG 检索 + 对话记忆
├── index.py               # 向量索引构建（多模型）
├── generate_explanation.py # 讲解预生成器（8种格式）
├── templates/             # chat / reader / notebook
├── static/                # echarts.min.js
├── .explanations/         # 预生成讲解 JSON（72文件）
└── chroma_db/             # 向量库存储
```

## 覆盖项目

索引了 6 个全栈项目的源码和 27 篇技术文档，力导向图可视化文件依赖关系：

- POS 日报推送系统 (Playwright + SQLite + 企微 Webhook)
- RFM 客户价值分析 (FastAPI + ECharts + CSV 解析)
- AI 短视频自动生成 (DeepSeek + Qwen VL + FFmpeg)
- 无人直播系统 (生产者-消费者 + edge-tts)
- 内网培训系统 (FastAPI + QR登录 + RBAC)
- 知识库助手自身 (ChromaDB + RAG)

## 版本

| 版本 | 标签 | 核心变化 |
|------|------|---------|
| V1 | v1.0 | RAG 基础链路（英文模型） |
| V2 | v2.0 | 换中文模型 + 多模型统一架构 |
| V3 | v3.1 | 增量索引 + 对话历史 + 项目筛选 + 导师模式 |
| V3.2 | v3.2 | 阅读模式 + 预生成讲解 + 笔记系统 |
| V3.3 | v3.3 | 力导向图交互改进 + 多语言讲解 + 6项目完整依赖图 |

## License

Private — 个人项目
