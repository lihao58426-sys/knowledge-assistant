"""
个人知识库助手 — Web 界面
用法：python server.py → http://localhost:8002
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from rag_engine import ask, get_session

from urllib.parse import quote as urlencode

app = FastAPI(title="知识库助手")
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
jinja_env = Environment(loader=FileSystemLoader("templates"))
jinja_env.filters["urlencode"] = urlencode

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    project = request.query_params.get("project", "")
    mode = request.query_params.get("mode", "search")

    # 导师模式 — 加载文件列表
    tutor_files = []
    if mode == "tutor" and project and project in PROJECT_ROOTS:
        root = PROJECT_ROOTS[project]
        for dirpath, _, filenames in _os.walk(root):
            if any(s in dirpath for s in ["__pycache__", ".git", "chroma_db", "build_tmp",
                                           "dist", "data", "uploads", "output", "materials", "temp"]):
                continue
            for f in filenames:
                if f.endswith((".py", ".md")):
                    tutor_files.append(_os.path.join(dirpath, f))
        tutor_files.sort()

    # 文档模式 — 加载 TO DO 文件夹
    doc_files = []
    if mode == "docs":
        todo = r"E:\Trae CN\AI-Kart-Live\TO DO"
        if _os.path.exists(todo):
            for f in sorted(_os.listdir(todo)):
                if f.endswith(".md"):
                    doc_files.append(_os.path.join(todo, f))

    return HTMLResponse(jinja_env.get_template("chat.html").render(
        request=request, active_project=project, mode=mode, tutor_files=tutor_files,
        doc_files=doc_files, projects=PROJECT_ROOTS.keys()))

@app.post("/ask")
async def api_ask(request: Request):
    form = await request.form()
    q = form.get("question", "").strip()
    project = request.query_params.get("project", "")
    if not q:
        return HTMLResponse(jinja_env.get_template("chat.html").render(
            request=request, error="请输入问题", active_project=project))

    session_id = request.client.host if request.client else "default"
    a = ask(q, session_id=session_id, project_filter=project)

    history = get_session(session_id)
    turns = len(history) // 2

    return HTMLResponse(jinja_env.get_template("chat.html").render(
        request=request, question=q, answer=a, turns=turns,
        active_project=project, mode="search", tutor_files=[], projects=PROJECT_ROOTS.keys()))

# ── 阅读模式（V3.2）：预生成讲解 → 左右联动 ──

@app.get("/reader", response_class=HTMLResponse)
async def reader_page(request: Request):
    """阅读模式 — 预生成讲解 + 目录跳转 + 双向联动"""
    import json as _json
    project = request.query_params.get("project", "")
    filepath = request.query_params.get("file", "")
    code_lines = []
    fname = ""
    has_explain = False
    explain_json = "null"

    if filepath and _os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            code_lines = f.read().split('\n')
        fname = _os.path.basename(filepath)

        # 查预生成讲解
        d = _os.path.dirname(filepath)
        parent = _os.path.basename(d)
        if parent == 'tests':
            parent = _os.path.basename(_os.path.dirname(d)) + '_tests'
        explain_path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            ".explanations", f"{parent}_{fname}.json"
        )
        if _os.path.exists(explain_path):
            with open(explain_path, "r", encoding="utf-8") as f:
                explain_json = f.read()
                has_explain = True

    return HTMLResponse(jinja_env.get_template("reader.html").render(
        request=request, project=project, filepath=filepath, fname=fname,
        code_json=_json.dumps(code_lines, ensure_ascii=False),
        filepath_json=_json.dumps(filepath, ensure_ascii=False) if filepath else '""',
        has_explain=has_explain,
        explain_json=explain_json,
    ))


# ── 导师模式：读整个文件 → 发给 DeepSeek 讲解 ──

import os as _os

PROJECT_ROOTS = {
    "pos_daily_report": r"E:\Trae CN\AI-Kart-Live\pos_daily_report",
    "rfm_report": r"E:\Trae CN\AI-Kart-Live\rfm_report",
    "auto_video": r"E:\Trae CN\AI-Kart-Live\auto_video",
    "live_stream": r"E:\Trae CN\AI-Kart-Live\live_stream",
    "内网培训系统demo": r"E:\Trae CN\AI-Kart-Live\内网培训系统demo",
    "knowledge-assistant": r"E:\Trae CN\AI-Kart-Live\knowledge-assistant",
}

@app.get("/tutor", response_class=HTMLResponse)
async def tutor_page(request: Request):
    """导师模式 — 选项目 → 选文件"""
    project = request.query_params.get("project", "")
    files = []
    if project and project in PROJECT_ROOTS:
        root = PROJECT_ROOTS[project]
        for dirpath, _, filenames in _os.walk(root):
            if any(s in dirpath for s in ["__pycache__", ".git", "chroma_db", "build_tmp", "dist", "data", "uploads", "output", "materials", "temp"]):
                continue
            for f in filenames:
                if f.endswith((".py", ".md")):
                    files.append(_os.path.join(dirpath, f))
        files.sort()
    return HTMLResponse(jinja_env.get_template("tutor.html").render(
        request=request, project=project, files=files, projects=PROJECT_ROOTS.keys()))


@app.post("/tutor/explain", response_class=HTMLResponse)
async def tutor_explain(request: Request):
    """读文件 → 发给 DeepSeek 讲解（支持多文件勾选）"""
    form = await request.form()
    question = form.get("question", "").strip()
    if not question:
        question = "请逐模块讲解这些文件：每个部分做什么、为什么这么设计、在这个项目中处于什么位置"

    # 获取勾选的文件列表
    filepaths = form.getlist("files")
    if not filepaths:
        # 兼容旧版单文件参数
        fp = form.get("file", "")
        if fp:
            filepaths = [fp]
    if not filepaths:
        return HTMLResponse("<h2 style='padding:40px;text-align:center'>请至少选择一个文件</h2>")

    # 读所有勾选的文件
    codes = []
    for fp in filepaths:
        if not _os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        codes.append(f"### {fp}\n```python\n{content}\n```")

    if not codes:
        return HTMLResponse("<h2 style='padding:40px;text-align:center'>文件不存在</h2>")

    all_code = "\n\n".join(codes)
    file_list = "\n".join(f"  - {f}" for f in filepaths)

    # 发给 DeepSeek
    import requests as _r
    headers = {
        "Authorization": f"Bearer {_os.getenv('DEEPSEEK_API_KEY', '')}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是技术导师。用户正在学习自己的项目代码。请用用户提供的文件内容来回答。要讲清楚：这段代码做什么、为什么这么写、不同文件之间怎么连接。引用具体的文件名和行号。鼓励用户继续追问。"},
            {"role": "user", "content": f"我选择了以下文件：\n{file_list}\n\n我的问题：{question}\n\n完整代码：\n\n{all_code}"},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }
    resp = _r.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data, timeout=180)
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"].strip()

    return HTMLResponse(jinja_env.get_template("tutor.html").render(
        request=request, project="", filepaths=filepaths, question=question,
        answer=answer, files=[], projects=PROJECT_ROOTS.keys(),
        code_preview=all_code[:3000] + ("..." if len(all_code) > 3000 else "")))


# ── 逐行讲解模式 ──

@app.get("/code-tutor", response_class=HTMLResponse)
async def code_tutor_page(request: Request):
    """代码逐行讲解页面"""
    project = request.query_params.get("project", "")
    filepath = request.query_params.get("file", "")
    code_lines = []
    fname = ""

    # 文件列表
    tutor_files = []
    if project and project in PROJECT_ROOTS:
        root = PROJECT_ROOTS[project]
        for dirpath, _, filenames in _os.walk(root):
            if any(s in dirpath for s in ["__pycache__", ".git", "chroma_db", "build_tmp",
                                           "dist", "data", "uploads", "output", "materials", "temp"]):
                continue
            for f in filenames:
                if f.endswith(".py"):
                    tutor_files.append(_os.path.join(dirpath, f))
        tutor_files.sort()

    # 如果有文件路径 → 读代码
    if filepath and _os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            code_lines = f.read().split('\n')
        fname = _os.path.basename(filepath)

    import json as _json
    return HTMLResponse(jinja_env.get_template("code-tutor.html").render(
        request=request, project=project,
        filepath=filepath, filepath_json=_json.dumps(filepath, ensure_ascii=False),
        fname=fname,
        code_json=_json.dumps(code_lines, ensure_ascii=False),
        tutor_files=tutor_files, tutor_files_json=_json.dumps(tutor_files, ensure_ascii=False),
        projects=PROJECT_ROOTS.keys(),
        mode="tutor", active_project=project))


@app.post("/code-tutor/explain")
async def code_tutor_explain(request: Request):
    """逐行讲解 API"""
    import json as _json, requests as _r
    form = await request.form()
    filepath = form.get("file", "")
    question = form.get("question", "").strip()
    context = form.get("context", "")

    if not filepath or not _os.path.exists(filepath):
        return HTMLResponse(_json.dumps({"error": "文件不存在"}), media_type="application/json")

    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    prompt = question
    if context:
        prompt = f"之前讲解的代码：\n{context}\n\n新问题：{question}"
    prompt += f"\n\n完整文件 ({_os.path.basename(filepath)}):\n```python\n{code}\n```\n\n请直接按 L行号 | 讲解内容 的格式输出，每行一条。"

    headers = {
        "Authorization": f"Bearer {_os.getenv('DEEPSEEK_API_KEY', '')}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是代码导师。用户正在逐行学习代码。请用格式 L行号 | 讲解内容 输出。每行一条，行号范围用 L1-4 表示多行。语言简洁，每行不超过两句话。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3, "max_tokens": 3000,
    }
    resp = _r.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data, timeout=120)
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"].strip()

    return HTMLResponse(_json.dumps({"answer": answer}, ensure_ascii=False), media_type="application/json")


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request):
    """笔记本页面 — 分项目/分文件查看所有笔记"""
    return HTMLResponse(jinja_env.get_template("notebook.html").render(request=request))


# ── 架构图 ──

# 每个项目的文件依赖关系（nodes=节点, links=连线）
GRAPH_DATA = {
    "pos_daily_report": {
        "nodes": [
            {"name":"main.py","category":0,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\main.py"},
            {"name":"config.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\config.py"},
            {"name":"crawler.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\crawler.py"},
            {"name":"models.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\models.py"},
            {"name":"database.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\database.py"},
            {"name":"report.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\report.py"},
            {"name":"pusher.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\pusher.py"},
            {"name":"exceptions.py","category":2,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\exceptions.py"},
            {"name":"config.yaml","category":2,"file":r"E:\Trae CN\AI-Kart-Live\pos_daily_report\config.yaml"},
        ],
        "links": [
            {"source":"main.py","target":"config.py"},
            {"source":"main.py","target":"crawler.py"},
            {"source":"main.py","target":"models.py"},
            {"source":"main.py","target":"database.py"},
            {"source":"main.py","target":"report.py"},
            {"source":"main.py","target":"pusher.py"},
            {"source":"crawler.py","target":"config.py"},
            {"source":"crawler.py","target":"exceptions.py"},
            {"source":"database.py","target":"models.py"},
            {"source":"report.py","target":"models.py"},
            {"source":"config.py","target":"config.yaml"},
        ]
    },
    "rfm_report": {
        "nodes": [
            {"name":"server.py","category":0,"file":r"E:\Trae CN\AI-Kart-Live\rfm_report\server.py"},
            {"name":"analysis.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\rfm_report\analysis.py"},
            {"name":"upload.html","category":1,"file":r"E:\Trae CN\AI-Kart-Live\rfm_report\templates\upload.html"},
            {"name":"report.html","category":1,"file":r"E:\Trae CN\AI-Kart-Live\rfm_report\templates\report.html"},
            {"name":"echarts.min.js","category":2,"file":""},
        ],
        "links": [
            {"source":"server.py","target":"analysis.py"},
            {"source":"server.py","target":"upload.html"},
            {"source":"server.py","target":"report.html"},
            {"source":"report.html","target":"echarts.min.js"},
        ]
    },
    "auto_video": {
        "nodes": [
            {"name":"main.py","category":0,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\main.py"},
            {"name":"config.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\config.py"},
            {"name":"platforms.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\platforms.py"},
            {"name":"materials.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\materials.py"},
            {"name":"script_gen.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\script_gen.py"},
            {"name":"voice.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\voice.py"},
            {"name":"scenes.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\scenes.py"},
            {"name":"compose.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\auto_video\compose.py"},
        ],
        "links": [
            {"source":"main.py","target":"config.py"},
            {"source":"main.py","target":"platforms.py"},
            {"source":"main.py","target":"materials.py"},
            {"source":"main.py","target":"script_gen.py"},
            {"source":"main.py","target":"voice.py"},
            {"source":"main.py","target":"compose.py"},
            {"source":"compose.py","target":"scenes.py"},
            {"source":"scenes.py","target":"config.py"},
            {"source":"voice.py","target":"config.py"},
            {"source":"materials.py","target":"config.py"},
            {"source":"script_gen.py","target":"config.py"},
        ]
    },
    "live_stream": {
        "nodes": [
            {"name":"main.py","category":0,"file":r"E:\Trae CN\AI-Kart-Live\live_stream\main.py"},
            {"name":"script_gen.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\live_stream\script_gen.py"},
            {"name":"tts.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\live_stream\tts.py"},
            {"name":"player.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\live_stream\player.py"},
        ],
        "links": [
            {"source":"main.py","target":"script_gen.py"},
            {"source":"main.py","target":"tts.py"},
            {"source":"main.py","target":"player.py"},
        ]
    },
    "knowledge-assistant": {
        "nodes": [
            {"name":"server.py","category":0,"file":r"E:\Trae CN\AI-Kart-Live\knowledge-assistant\server.py"},
            {"name":"index.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\knowledge-assistant\index.py"},
            {"name":"rag_engine.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\knowledge-assistant\rag_engine.py"},
            {"name":"generate_explanation.py","category":1,"file":r"E:\Trae CN\AI-Kart-Live\knowledge-assistant\generate_explanation.py"},
            {"name":"chat.html","category":1,"file":""},
            {"name":"reader.html","category":1,"file":""},
            {"name":"notebook.html","category":1,"file":""},
        ],
        "links": [
            {"source":"server.py","target":"rag_engine.py"},
            {"source":"server.py","target":"chat.html"},
            {"source":"server.py","target":"reader.html"},
            {"source":"server.py","target":"notebook.html"},
            {"source":"rag_engine.py","target":"index.py"},
            {"source":"generate_explanation.py","target":"rag_engine.py"},
        ]
    },
}

@app.get("/arch", response_class=HTMLResponse)
async def arch_page(request: Request):
    project = request.query_params.get("project", "pos_daily_report")
    import json as _json
    graph = GRAPH_DATA.get(project, {"nodes":[],"links":[]})
    return HTMLResponse(jinja_env.get_template("arch.html").render(
        request=request, active=project, projects=list(GRAPH_DATA.keys()),
        graph_json=_json.dumps(graph, ensure_ascii=False)))


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  个人知识库助手 V3")
    print("  http://localhost:8002")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8002)
