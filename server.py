"""
个人知识库助手 — Web 界面
用法：python server.py → http://localhost:8002
"""

import os
import json
import secrets
import base64

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from rag_engine import ask, get_session

from urllib.parse import quote as urlencode

# ── 路径配置 ──
# 工作区根目录 = 本文件所在目录的上一级（knowledge-assistant 住在工作区里面）。
# 换电脑/上云后目录结构不同时，可用环境变量 KA_WORKSPACE_ROOT 手动指定，不用改代码。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.getenv("KA_WORKSPACE_ROOT", os.path.dirname(BASE_DIR))


def safe_path(filepath: str) -> str | None:
    """路径白名单校验：防任意文件读取。

    把用户传来的路径解析成真实绝对路径（../ 等绕路手法会被展开），
    然后检查它是否在工作区内。在 → 返回真实路径；不在 → 返回 None（调用方拒绝）。
    """
    if not filepath:
        return None
    real = os.path.realpath(filepath)
    root = os.path.realpath(WORKSPACE_ROOT)
    # normcase: Windows 路径不分大小写，统一后再比较，防止大小写绕过
    if not os.path.normcase(real).startswith(os.path.normcase(root + os.sep)):
        return None
    return real


# ── 访问鉴权 ──
# 上云后必须设 KA_PASSWORD，所有页面需要密码才能访问。
# 本地开发时不设 → 跳过鉴权，跟以前一样用。
KA_PASSWORD = os.getenv("KA_PASSWORD", "")


def _check_auth(request: Request) -> bool:
    """检查请求是否带了正确的密码。没设密码时直接放行（本地模式）。"""
    if not KA_PASSWORD:
        return True  # 没设密码 = 本地开发模式，不拦

    # HTTP Basic Auth: "Basic base64(username:password)"
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        _, password = decoded.split(":", 1)
        # 用 compare_digest 防时序攻击——两万标准程序员该知道的细节
        return secrets.compare_digest(password, KA_PASSWORD)
    except Exception:
        return False


app = FastAPI(title="知识库助手")

# ── 鉴权中间件 ──
# 每个请求先验证密码，不过的返回 401
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not _check_auth(request):
        return JSONResponse({"detail": "请输入密码"}, status_code=401,
                          headers={"WWW-Authenticate": 'Basic realm="Knowledge Assistant"'})
    return await call_next(request)

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
        for dirpath, _, filenames in os.walk(root):
            if any(s in dirpath for s in ["__pycache__", ".git", "chroma_db", "build_tmp",
                                           "dist", "data", "uploads", "output", "materials", "temp"]):
                continue
            for f in filenames:
                if f.endswith((".py", ".md")):
                    tutor_files.append(os.path.join(dirpath, f))
        tutor_files.sort()

    # 文档模式 — 加载 TO DO 文件夹
    doc_files = []
    if mode == "docs":
        todo = os.path.join(WORKSPACE_ROOT, "TO DO")
        if os.path.exists(todo):
            for f in sorted(os.listdir(todo)):
                if f.endswith(".md"):
                    doc_files.append(os.path.join(todo, f))

    return HTMLResponse(jinja_env.get_template("chat.html").render(
        request=request, active_project=project, mode=mode, tutor_files=tutor_files,
        doc_files=doc_files, projects=PROJECT_ROOTS.keys(),
        arch_json=json.dumps(GRAPH_DATA, ensure_ascii=False)))

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
    project = request.query_params.get("project", "")
    filepath = safe_path(request.query_params.get("file", ""))  # 白名单校验，工作区外一律拒绝
    code_lines = []
    fname = ""
    has_explain = False
    explain_json = "null"

    if filepath and os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            code_lines = f.read().split('\n')
        fname = os.path.basename(filepath)

        # 查预生成讲解
        d = os.path.dirname(filepath)
        parent = os.path.basename(d)
        if parent == 'tests':
            parent = os.path.basename(os.path.dirname(d)) + '_tests'
        explain_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".explanations", f"{parent}_{fname}.json"
        )
        if os.path.exists(explain_path):
            with open(explain_path, "r", encoding="utf-8") as f:
                explain_json = f.read()
                has_explain = True

    code_json_str = json.dumps(code_lines, ensure_ascii=False)
    fp_json_str = json.dumps(filepath, ensure_ascii=False) if filepath else '""'
    # 防止代码内含 <script> 或 </script> 破坏 HTML script 标签
    # <script → \x3Cscript (JS hex转义), </ → <\/ (JSON/JS通用)
    code_json_str = code_json_str.replace('<script', '\\x3Cscript').replace('</', '<\\/')
    fp_json_str = fp_json_str.replace('</', '<\\/')
    if explain_json:
        explain_json = explain_json.replace('<script', '\\x3Cscript').replace('</', '<\\/')
    return HTMLResponse(jinja_env.get_template("reader.html").render(
        request=request, project=project, filepath=filepath, fname=fname,
        code_json=code_json_str,
        filepath_json=fp_json_str,
        has_explain=has_explain,
        explain_json=explain_json,
    ))


# ── 导师模式：读整个文件 → 发给 DeepSeek 讲解 ──

# 六个项目的根目录，都挂在工作区下，按名字拼出来
_PROJECT_NAMES = ["pos_daily_report", "rfm_report", "auto_video",
                  "live_stream", "内网培训系统demo", "knowledge-assistant"]
PROJECT_ROOTS = {name: os.path.join(WORKSPACE_ROOT, name) for name in _PROJECT_NAMES}

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

    # 读所有勾选的文件（safe_path 白名单校验，工作区外的路径直接跳过）
    codes = []
    for fp in filepaths:
        fp = safe_path(fp)
        if not fp or not os.path.exists(fp):
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
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY', '')}",
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

    return HTMLResponse(jinja_env.get_template("chat.html").render(
        request=request, question=question, answer=answer,
        active_project="", mode="tutor", tutor_files=[], doc_files=[],
        projects=PROJECT_ROOTS.keys(), arch_json=json.dumps(GRAPH_DATA, ensure_ascii=False)))


# ── 追问 API（reader 和 notebook 共用）──

@app.post("/code-tutor/explain")
async def code_tutor_explain(request: Request):
    """逐行讲解 API"""
    import requests as _r
    form = await request.form()
    filepath = safe_path(form.get("file", ""))  # 白名单校验，工作区外一律拒绝
    question = form.get("question", "").strip()
    context = form.get("context", "")

    if not filepath or not os.path.exists(filepath):
        return HTMLResponse(json.dumps({"error": "文件不存在"}), media_type="application/json")

    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    prompt = question
    if context:
        prompt = f"之前讲解的代码：\n{context}\n\n新问题：{question}"
    prompt += f"\n\n完整文件 ({os.path.basename(filepath)}):\n```python\n{code}\n```\n\n请直接按 L行号 | 讲解内容 的格式输出，每行一条。"

    headers = {
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY', '')}",
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

    return HTMLResponse(json.dumps({"answer": answer}, ensure_ascii=False), media_type="application/json")


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request):
    """笔记本页面 — 分项目/分文件查看所有笔记"""
    return HTMLResponse(jinja_env.get_template("notebook.html").render(request=request))


# ── 架构图 ──

# 每个项目的文件依赖关系（nodes=节点, links=连线）
GRAPH_DATA = {
    "pos_daily_report": {
        "nodes": [
            {"name":"main.py","category":0,"tech":"调度入口 · APScheduler · 自调度算法","file":"pos_daily_report/main.py"},
            {"name":"config.py","category":1,"tech":"YAML 配置管理 · 多店支持","file":"pos_daily_report/config.py"},
            {"name":"crawler.py","category":1,"tech":"Playwright · 反检测 · 自动登录","file":"pos_daily_report/crawler.py"},
            {"name":"models.py","category":1,"tech":"dataclass · 类型定义","file":"pos_daily_report/models.py"},
            {"name":"database.py","category":1,"tech":"SQLite · CRUD · 历史查询","file":"pos_daily_report/database.py"},
            {"name":"report.py","category":1,"tech":"报告生成 · 环比计算","file":"pos_daily_report/report.py"},
            {"name":"pusher.py","category":1,"tech":"企业微信 Webhook · Markdown","file":"pos_daily_report/pusher.py"},
            {"name":"exceptions.py","category":2,"tech":"自定义异常类","file":"pos_daily_report/exceptions.py"},
            {"name":"config.yaml","category":2,"tech":"多店铺配置数据","file":"pos_daily_report/config.yaml"},
            {"name":"business_overview.html","category":2,"tech":"营业概况 · ECharts 仪表盘","file":"pos_daily_report/business_overview.html"},
            {"name":"overview_page.html","category":2,"tech":"数据总览 · 多店对比","file":"pos_daily_report/overview_page.html"},
            {"name":"product_sales.html","category":2,"tech":"商品销售排名 · 趋势图","file":"pos_daily_report/product_sales.html"},
        ],
        "links": [
            {"source":"main.py","target":"config.py"},
            {"source":"main.py","target":"crawler.py"},
            {"source":"main.py","target":"models.py"},
            {"source":"main.py","target":"database.py"},
            {"source":"main.py","target":"report.py"},
            {"source":"main.py","target":"pusher.py"},
            {"source":"main.py","target":"business_overview.html"},
            {"source":"main.py","target":"overview_page.html"},
            {"source":"main.py","target":"product_sales.html"},
            {"source":"crawler.py","target":"config.py"},
            {"source":"crawler.py","target":"exceptions.py"},
            {"source":"database.py","target":"models.py"},
            {"source":"report.py","target":"models.py"},
            {"source":"config.py","target":"config.yaml"},
        ]
    },
    "rfm_report": {
        "nodes": [
            {"name":"server.py","category":0,"tech":"FastAPI · 路由 · 文件上传","file":"rfm_report/server.py"},
            {"name":"analysis.py","category":1,"tech":"RFM 分群 · CLV · 留存曲线","file":"rfm_report/analysis.py"},
            {"name":"charts.js","category":1,"tech":"ECharts 柱状图 · 饼图 · 折线图","file":"rfm_report/charts.js"},
            {"name":"rfm.js","category":1,"tech":"RFM 计算 · 8类分群算法","file":"rfm_report/rfm.js"},
            {"name":"config.js","category":1,"tech":"前端配置 · 图表颜色常量","file":"rfm_report/config.js"},
            {"name":"upload.html","category":1,"tech":"CSV 上传 · Jinja2 模板","file":"rfm_report/templates/upload.html"},
            {"name":"report.html","category":1,"tech":"分析报告 · ECharts 可视化","file":"rfm_report/templates/report.html"},
            {"name":"echarts.min.js","category":2,"tech":"ECharts 图表库","file":"rfm_report/static/echarts.min.js"},
        ],
        "links": [
            {"source":"server.py","target":"analysis.py"},
            {"source":"server.py","target":"upload.html"},
            {"source":"server.py","target":"report.html"},
            {"source":"report.html","target":"echarts.min.js"},
            {"source":"report.html","target":"charts.js"},
            {"source":"report.html","target":"rfm.js"},
            {"source":"report.html","target":"config.js"},
            {"source":"charts.js","target":"config.js"},
            {"source":"rfm.js","target":"config.js"},
            {"source":"charts.js","target":"rfm.js"},
        ]
    },
    "auto_video": {
        "nodes": [
            {"name":"main.py","category":0,"tech":"流程编排入口","file":"auto_video/main.py"},
            {"name":"config.py","category":1,"tech":"配置管理 · 三平台参数","file":"auto_video/config.py"},
            {"name":"platforms.py","category":1,"tech":"抖音 · 小红书 · 视频号差异化","file":"auto_video/platforms.py"},
            {"name":"materials.py","category":1,"tech":"Qwen VL · 素材扫描识别","file":"auto_video/materials.py"},
            {"name":"script_gen.py","category":1,"tech":"DeepSeek · AI 脚本生成","file":"auto_video/script_gen.py"},
            {"name":"voice.py","category":1,"tech":"edge-tts · 语音合成","file":"auto_video/voice.py"},
            {"name":"scenes.py","category":1,"tech":"场景模板 · 转场效果","file":"auto_video/scenes.py"},
            {"name":"compose.py","category":1,"tech":"FFmpeg · 视频合成","file":"auto_video/compose.py"},
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
            {"name":"main.py","category":0,"tech":"生产者-消费者模式 · 调度入口","file":"live_stream/main.py"},
            {"name":"script_gen.py","category":1,"tech":"DeepSeek · 口播话术生成","file":"live_stream/script_gen.py"},
            {"name":"tts.py","category":1,"tech":"edge-tts · 多音色轮换","file":"live_stream/tts.py"},
            {"name":"player.py","category":1,"tech":"pygame · 无缝音频播放","file":"live_stream/player.py"},
        ],
        "links": [
            {"source":"main.py","target":"script_gen.py"},
            {"source":"main.py","target":"tts.py"},
            {"source":"main.py","target":"player.py"},
        ]
    },
    "knowledge-assistant": {
        "nodes": [
            {"name":"server.py","category":0,"tech":"FastAPI · Web 服务 · 路由","file":"knowledge-assistant/server.py"},
            {"name":"index.py","category":1,"tech":"ChromaDB · 向量索引 · 切片","file":"knowledge-assistant/index.py"},
            {"name":"rag_engine.py","category":1,"tech":"RAG 引擎 · DeepSeek · 对话记忆","file":"knowledge-assistant/rag_engine.py"},
            {"name":"generate_explanation.py","category":1,"tech":"DeepSeek · 讲解预生成","file":"knowledge-assistant/generate_explanation.py"},
            {"name":"chat.html","category":1,"tech":"ECharts 力导向图 · Jinja2","file":"knowledge-assistant/templates/chat.html"},
            {"name":"reader.html","category":1,"tech":"代码阅读器 · 逐行讲解联动","file":"knowledge-assistant/templates/reader.html"},
            {"name":"notebook.html","category":1,"tech":"笔记系统 · localStorage","file":"knowledge-assistant/templates/notebook.html"},
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
    "内网培训系统demo": {
        "nodes": [
            {"name":"server.py","category":0,"tech":"FastAPI · QR登录 · RBAC · PyInstaller","file":"内网培训系统demo/server.py"},
            {"name":"database.py","category":1,"tech":"SQLAlchemy · SQLite · bcrypt","file":"内网培训系统demo/database.py"},
            {"name":"login.html","category":1,"tech":"QR码扫码 · 双向确认","file":"内网培训系统demo/templates/login.html"},
            {"name":"admin_dashboard.html","category":1,"tech":"管理后台 · 数据总览","file":"内网培训系统demo/templates/admin_dashboard.html"},
            {"name":"study.html","category":1,"tech":"学习页面 · 断点续学","file":"内网培训系统demo/templates/study.html"},
            {"name":"quiz.html","category":1,"tech":"题库考试 · 自动判分","file":"内网培训系统demo/templates/quiz.html"},
            {"name":"base.html","category":2,"tech":"Jinja2 基础模板","file":"内网培训系统demo/templates/base.html"},
            {"name":"main.js","category":2,"tech":"前端交互逻辑","file":"内网培训系统demo/static/js/main.js"},
            {"name":"style.css","category":2,"tech":"全局样式","file":"内网培训系统demo/static/css/style.css"},
        ],
        "links": [
            {"source":"server.py","target":"database.py"},
            {"source":"server.py","target":"login.html"},
            {"source":"server.py","target":"admin_dashboard.html"},
            {"source":"server.py","target":"study.html"},
            {"source":"server.py","target":"quiz.html"},
            {"source":"login.html","target":"base.html"},
            {"source":"admin_dashboard.html","target":"base.html"},
            {"source":"study.html","target":"base.html"},
            {"source":"quiz.html","target":"base.html"},
            {"source":"base.html","target":"main.js"},
            {"source":"base.html","target":"style.css"},
        ]
    },
}

# GRAPH_DATA 里存的是相对路径，启动时统一拼上工作区根目录，换环境不用改数据
for _proj in GRAPH_DATA.values():
    for _node in _proj["nodes"]:
        _node["file"] = os.path.join(WORKSPACE_ROOT, _node["file"])

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  个人知识库助手 V3")
    print("  http://localhost:8002")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8002)
