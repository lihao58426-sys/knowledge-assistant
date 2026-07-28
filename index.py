"""
知识库索引构建器（多模型支持）
==============================
扫描 → 切片 → 自选模型向量化 → ChromaDB

用法：
  python index.py              默认中文模型，全量重建
  python index.py --v1          英文模型
  python index.py --incremental 增量更新（只处理变动的文件）
"""

import os
import re

# ── 离线模型加载 ──
# sentence-transformers 默认每次加载模型都会联网到 huggingface.co 检查更新。
# 国内网络连不上，会导致加载卡住数分钟（连接超时后重试 5 次）。
# 模型已缓存在本地，这里强制离线，直接读缓存。
# 上云若需联网下载模型，可在启动前设 HF_HUB_OFFLINE=0 覆盖此默认值。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import sys
import hashlib
import json
import chromadb
from chromadb.api.types import EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

# ── 配置 ──
# 工作区根目录 = 本文件所在目录的上一级；上云换目录时用环境变量 KA_WORKSPACE_ROOT 覆盖
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.getenv("KA_WORKSPACE_ROOT", os.path.dirname(BASE_DIR))

SCAN_DIRS = [os.path.join(WORKSPACE_ROOT, name) for name in [
    "TO DO",
    "pos_daily_report",
    "rfm_report",
    "auto_video",
    "live_stream",
    "内网培训系统demo",
]]

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ── 模型注册表（加新模型只需加一行）──
MODELS = {
    "v1": {
        "name": "all-MiniLM-L6-v2",
        "source": "sentence-transformers/all-MiniLM-L6-v2",
        "lang": "英文",
        "chroma_dir": "./chroma_db",
        "collection": "knowledge_base_v1",
    },
    "v2": {
        "name": "text2vec-base-chinese",
        "source": "shibing624/text2vec-base-chinese",
        "lang": "中文",
        "chroma_dir": "./chroma_db",
        "collection": "knowledge_base_v2",
    },
}

FINGERPRINT_FILE = "./.index_fingerprint.json"  # 记录每个文件的修改时间和哈希


def _file_fingerprint(path: str) -> str:
    """计算文件的 md5 + 修改时间"""
    stat = os.stat(path)
    return f"{stat.st_mtime}-{stat.st_size}"


def _load_fingerprints() -> dict:
    """加载上次索引时的文件指纹"""
    if os.path.exists(FINGERPRINT_FILE):
        with open(FINGERPRINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_fingerprints(fingerprints: dict):
    """保存当前文件指纹"""
    with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
        json.dump(fingerprints, f, indent=2, ensure_ascii=False)


SKIP_DIRS = ["__pycache__", ".git", ".pytest_cache", "node_modules",
             "venv", "temp", "output", "materials", "build_tmp",
             "dist", "data", "uploads", "chroma_db_v1", "chroma_db_v2"]


class ModelEmbedding(EmbeddingFunction):
    """通用 embedding 包装器——模型名字决定一切"""
    def __init__(self, model_source: str):
        print(f"  加载模型: {model_source}...")
        self.model = SentenceTransformer(model_source)

    def __call__(self, texts: list[str]) -> Embeddings:
        return self.model.encode(texts).tolist()


def scan_files(dirs: list) -> list:
    files = []
    for d in dirs:
        if not os.path.exists(d):
            print(f"  [跳过] {d}")
            continue
        for root, _, filenames in os.walk(d):
            if any(s in root for s in SKIP_DIRS):
                continue
            for f in filenames:
                if f.endswith((".py", ".md")):
                    files.append(os.path.join(root, f))
    return files


def _chunk_simple(text: str, source: str, offset: int = 0) -> list:
    """滑动窗口切分——固定 800 字符 + 100 overlap。给通用文件类型用。

    offset: 字符位置偏移——当被 _chunk_code/_chunk_markdown 退回调用时，
           确保不同 section 的 position 不冲突。
    """
    chunks = []
    text = text.strip()
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        segment = text[start:end].strip()
        if segment:
            chunks.append({
                "text": segment,
                "source": source,
                "position": f"{offset + start}-{offset + end}"
            })
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _chunk_markdown(text: str, source: str) -> list:
    """Markdown 文档切分——先按 ## 标题边界拆，长段退回滑动窗口

    思路：一个 ## 标题 = 一个知识点。在标题处断不会把两个主题混在一起。
    短段（≤800 字符）整段作为一个 chunk，长段用滑动窗口补切。
    """
    chunks = []
    # 按 ## 标题拆——保留标题跟后续内容在一起
    sections = re.split(r'\n(?=## )', text)
    offset = 0
    for idx, sec in enumerate(sections):
        sec = sec.strip()
        if not sec:
            offset += len(sections[idx]) + 1  # +1 for the \n that was consumed
            continue
        if len(sec) <= CHUNK_SIZE:
            chunks.append({"text": sec, "source": source, "position": f"md-section-{idx}"})
        else:
            # 段落太长 → 退回滑动窗口（带 offset，避免 position 冲突）
            chunks.extend(_chunk_simple(sec, source, offset=offset))
        offset += len(sections[idx]) + 1
    return chunks


def _chunk_code(text: str, source: str) -> list:
    """Python 代码切分——按 def/class 函数边界，不在函数中间切断

    用正则找到所有 def/class/async def 的行位置作为切分点。
    相邻切分点之间 = 一个函数 = 一个 chunk。
    单个函数超过 CHUNK_SIZE → 退回滑动窗口。
    """
    chunks = []
    lines = text.split('\n')
    # 找到所有函数/类定义行
    boundaries = [i for i, line in enumerate(lines)
                  if re.match(r'^(async def |def |class )', line.strip())]

    if not boundaries:
        # 没有函数/类定义 → 退回简单切分
        return _chunk_simple(text, source)

    # 第一个边界之前的代码（imports、注释等）→ 单独一个 chunk
    if boundaries[0] > 0:
        header = '\n'.join(lines[:boundaries[0]]).strip()
        if header:
            chunks.append({"text": header, "source": source, "position": f"0-{boundaries[0]}"})

    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(lines)
        block = '\n'.join(lines[start:end]).strip()
        if not block:
            continue
        if len(block) <= CHUNK_SIZE:
            chunks.append({"text": block, "source": source, "position": f"L{start}-L{end}"})
        else:
            # 单个函数太长 → 退回滑动窗口（偏移用行号估算）
            char_offset = sum(len(lines[k]) + 1 for k in range(start))
            chunks.extend(_chunk_simple(block, source, offset=char_offset))

    return chunks


def chunk_text(text: str, source: str) -> list:
    """文档切片——总入口。按文件类型分发到不同策略：
        .py → _chunk_code()      按函数/类边界
        .md → _chunk_markdown()  按 ## 标题边界
        其他 → _chunk_simple()   滑动窗口（原逻辑）
    """
    if source.endswith('.py'):
        return _chunk_code(text, source)
    elif source.endswith('.md'):
        return _chunk_markdown(text, source)
    else:
        return _chunk_simple(text, source)


def build_index(model_key: str = "v2", incremental: bool = False):
    """用指定模型构建索引"""
    cfg = MODELS[model_key]

    mode = "增量更新" if incremental else "全量重建"
    print("=" * 50)
    print(f"  知识库索引构建器（{cfg['lang']}模型 {cfg['name']}）{mode}")
    print("=" * 50)

    # [1/4] 扫描
    print("\n[1/4] 扫描文件...")
    files = scan_files(SCAN_DIRS)
    print(f"  找到 {len(files)} 个文件")
    if not files:
        return

    # 增量模式：过滤未变动的文件
    old_fps = _load_fingerprints() if incremental else {}
    new_fps = {}

    if incremental and old_fps:
        changed_files = []
        skipped = 0
        for path in files:
            fp = _file_fingerprint(path)
            new_fps[path] = fp
            if old_fps.get(path) == fp:
                skipped += 1
            else:
                changed_files.append(path)
        print(f"  跳过 {skipped} 个未变动的文件，需处理 {len(changed_files)} 个")
        files = changed_files

    # [2/4] 读取 + 切段
    print("\n[2/4] 读取并切段...")
    all_chunks = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            chunks = chunk_text(content, path)
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"  [跳过] {path} ({e})")
    print(f"  共切出 {len(all_chunks)} 个片段")

    # [3/4] 连接 ChromaDB + 加载模型
    print(f"\n[3/4] 加载 {cfg['lang']}模型...")
    client = chromadb.PersistentClient(path=cfg["chroma_dir"])
    embed_fn = ModelEmbedding(cfg["source"])

    if incremental:
        # 增量模式：保留旧 collection，只删变动文件的旧片段（按 source 过滤）
        try:
            collection = client.get_collection(cfg["collection"], embedding_function=embed_fn)
            # 删除变动文件对应的旧片段
            for f in files:
                try:
                    collection.delete(where={"source": f})
                except Exception:
                    pass
            print(f"  已删除 {len(files)} 个变动文件的旧索引")

            # 检出本地已删除的文件，从 Chroma 中也删掉
            current_set = set(scan_files(SCAN_DIRS))
            deleted = [path for path in old_fps if path not in current_set]
            if deleted:
                print(f"  检测到 {len(deleted)} 个已删除文件，清理索引...")
                for path in deleted:
                    try:
                        collection.delete(where={"source": path})
                    except Exception:
                        pass
                    old_fps.pop(path, None)
                print(f"  已清理 {len(deleted)} 个")
        except Exception:
            # collection 不存在 → 创建新的
            collection = client.create_collection(
                name=cfg["collection"],
                embedding_function=embed_fn,
            )
    else:
        # 全量模式：删旧建新
        try:
            client.delete_collection(cfg["collection"])
            print("  已删除旧索引")
        except Exception:
            pass
        collection = client.create_collection(
            name=cfg["collection"],
            embedding_function=embed_fn,
        )

    # [4/4] 批量写入
    print(f"\n[4/4] 写入向量（每批 100 条）...")
    BATCH = 100
    texts = [c["text"] for c in all_chunks]
    metas = [{"source": c["source"], "position": c["position"]} for c in all_chunks]
    ids = [f"{model_key}c{hashlib.md5(c['source'].encode()+str(c['position']).encode()).hexdigest()[:12]}" for c in all_chunks]

    for i in range(0, len(all_chunks), BATCH):
        j = min(i + BATCH, len(all_chunks))
        collection.add(documents=texts[i:j], metadatas=metas[i:j], ids=ids[i:j])
        print(f"  {j}/{len(all_chunks)}", end="\r")

    # 保存文件指纹
    if not incremental:
        new_fps = {path: _file_fingerprint(path) for path in files}
    _save_fingerprints(new_fps)

    print(f"\n  完成！共 {len(all_chunks)} 个片段已索引")
    print(f"  索引位置: {os.path.abspath(cfg['chroma_dir'])}")
    print("=" * 50)


if __name__ == "__main__":
    inc = "--incremental" in sys.argv
    if "--v1" in sys.argv:
        build_index("v1", incremental=inc)
    else:
        build_index("v2", incremental=inc)
