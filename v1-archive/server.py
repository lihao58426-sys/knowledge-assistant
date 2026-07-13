"""
个人知识库助手 — FastAPI 服务器
==============================
用法：python server.py → 浏览器打开 http://localhost:8002
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from rag_engine import ask

app = FastAPI(title="个人知识库助手")
jinja_env = Environment(loader=FileSystemLoader("templates"))

def render(name: str, **kwargs) -> HTMLResponse:
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(**kwargs))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render("chat.html", request=request)


@app.post("/ask")
async def api_ask(request: Request):
    form = await request.form()
    question = form.get("question", "").strip()
    if not question:
        return render("chat.html", request=request, error="请输入问题")
    answer = ask(question)
    return render("chat.html", request=request, question=question, answer=answer)


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  个人知识库助手")
    print("  本机: http://localhost:8002")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8002)
