# 实验报告 — RAG 知识库助手 V1

> 实验日期：2026年7月12日
> 结论：技术链路跑通，检索质量受限于英文模型，V2 必须换中文 embedding

---

## 一、实验目的

验证"基于自己项目代码和技术文档的个人 RAG 知识库助手"是否技术上可行。回答三个问题：
1. 能不能把 `.py` 和 `.md` 文件自动索引到向量库
2. 能不能通过语义搜索找到相关片段
3. DeepSeek 能不能基于检索结果给出有依据的回答

## 二、技术方案

```
技术栈：
  ChromaDB（向量库）+ 本地 embedding 模型（all-MiniLM-L6-v2，79MB）
  + DeepSeek Chat API（问答生成）
  + FastAPI + Jinja2（网页界面）

数据流：
  TO DO/*.md + 项目/*.py → index.py 切段 → embedding 向量化 → ChromaDB
  用户提问 → 向量化 → ChromaDB 检索 Top 5 → + 问题 → DeepSeek → 回答 + 引用来源
```

## 三、构建过程

### 3.1 扫描 + 切段

```
扫描目录: 6 个项目文件夹
找到文件: 66 个（.py + .md）
切出片段: 480 个（800字/段，100字重叠）
```

### 3.2 向量化 + 存库

ChromaDB 自带免费的 `all-MiniLM-L6-v2` 本地模型（79MB）。第一次运行自动下载。

**下载模型踩坑历程：**
1. 直连 HuggingFace → 速度 50KB/s，超时断开
2. 开 VPN → 依旧慢，40KB/s，下了 25MB 后断开
3. 换国内镜像 `hf-mirror.com` → 略快，但下载到 62MB 后又断开
4. 换 VPN 节点 → 终于成功，约 3 分钟下完 79MB

**模型存储位置问题：** ChromaDB 硬编码缓存到 `C:\Users\xxx\.cache\chroma\`，不认 `HF_HOME` 环境变量。79MB 占用不大，暂接受。如需迁移用 Windows `mklink /J` 符号链接。

### 3.3 构建完成

```
[1/4] 扫描文件...  找到 66 个文件
[2/4] 读取并切段... 共切出 480 个片段
[3/4] 连接 ChromaDB... 已删除旧索引
[4/4] 写入向量... 480/480 完成
```

## 四、测试结果

### 4.1 成功的提问

| 问题 | 回答质量 | 来源准确性 |
|------|:--:|:--:|
| "介绍一下你的知识库" | ✅ 好 | ✅ 5 个真实文档 |
| "crawler.py 反检测做了什么" | ⚠️ 答案对，来源不精准 | ❌ 引用了 RAG 文档而非 crawler.py 源码 |

### 4.2 失败的提问

| 问题 | 现象 | 原因 |
|------|------|------|
| "多店支持是怎么实现的" | 完全没找到，来源全是无关文档 | 英文模型不理解中文"多店支持"的语义 |
| "怎么写爬虫" | 没参考 | 知识库没有爬虫教程，回答"资料中没有相关信息"——这个反而是正确的 |
| "playwright 的框架是什么" | 回答了 Playwright 是什么但说"没提到框架" | 同上，知识库没有这方面的文档 |

### 4.3 检索质量诊断

对"多店支持是怎么实现的"做检索源分析：

```
实际检索到的 5 个来源：
  1. Agent探索任务清单.md      ← 完全不相关
  2. unittest.mock模拟测试.md  ← 完全不相关
  3. exceptions.py             ← 完全不相关
  4. 任务清单-技术侧+业务侧.md  ← 略相关（提到了多店任务）
  5. 业务侧任务-细化执行清单.md ← 不相关

应该检索到的：
  1. 知识点总结-多店支持.md    ← 专门讲多店实现的
  2. config.yaml               ← stores 配置
  3. database.py               ← store_id 字段
  4. main.py                   ← 多店循环逻辑
```

**根因确认：** `all-MiniLM-L6-v2` 是英文模型。中文"多店支持"和"store_id""stores 列表"之间的语义联系它理解不了。**V2 必须换中文模型。**

## 五、遇到的全部问题

| # | 问题 | 原因 | 解决 | 耗时 |
|:--:|------|------|------|:--:|
| 1 | ChromaDB 模型下载超时 | HuggingFace 国内直连慢 | 换 VPN 节点 | ~40min |
| 2 | `HF_HOME` 不生效 | ChromaDB 不用这个变量 | 接受 C 盘存储 | 10min |
| 3 | `HF_ENDPOINT` 镜像下载还是慢 | hf-mirror 带宽有限 | 放弃镜像，换 VPN | 15min |
| 4 | 下载到 75% 断开 | 网络不稳定 | 重试 | 重复 3 次 |
| 5 | DeepSeek 没有 embedding API（404） | 我猜错了，没查文档 | 回退到本地模型 | 10min |
| 6 | C 盘空间从 11GB 掉到 4.3GB | pip 缓存 + 临时文件 + ChromaDB 模型 | 清理 pip+temp，ChromaDB 166MB 保留 | 10min |
| 7 | 终端打印 emoji 报错 | Windows GBK 编码 | 去掉 emoji | 2min |
| 8 | CLI 测试回答被截断 | 终端编码 | 写到文件再读 | 5min |
| 9 | 英文模型中文检索不准 | 本地模型语言不匹配 | V2 换中文模型 | 待解决 |

## 六、体验效果评价

### 好的方面

- **技术链路完全跑通。** 索引→检索→生成→网页，四步全链条可用
- **能回答知识库里有且明确的提问。** "反检测做了什么"能答对
- **来源引用机制有效。** 每个回答自动附带参考文件列表
- **回答诚实。** 知识库里没有的内容不会瞎编

### 差的方面

- **中文检索基本不可用。** 英文模型对中文问题的匹配准确率太低
- **来源经常引错文件。** 答案对了但引用的不是原始代码
- **网页版首次加载极慢。** 要加载 166MB 模型到内存
- **没有任何对话记忆。** 无法追问

## 七、V2 升级计划

### P0（必须）

| 升级 | 方案 | 预期效果 |
|------|------|---------|
| 换中文 embedding 模型 | `BAAI/bge-small-zh-v1.5` 或 `shibing624/text2vec-base-chinese` | 中文检索准确率大幅提升 |

### P1（重要）

| 升级 | 方案 |
|------|------|
| 增量索引 | 文件修改时间比较，只更新变的文件 |
| 对话历史 | 保留最近 10 轮上下文 |
| 来源去重 | 同一文件只显示一次，标注出现次数 |

### P2（锦上添花）

| 升级 | 方案 |
|------|------|
| 文件角色表 | 手动标注每个文件的功能/上下游 |
| 自动待办 | 对话结束生成待验证事项 |
| 手机 webhook | 接入企微机器人 |

---

---

## 八、V2 实验（2026年7月12日）

### 8.1 改动

一行代码：模型从 `all-MiniLM-L6-v2`（英文，79MB）换成 `text2vec-base-chinese`（中文，400MB）。

同时重构为多模型统一架构——`index.py` 和 `rag_engine.py` 共用一套扫描/切段/存库逻辑，模型通过 MODELS 注册表切换：

```python
MODELS = {
    "v1": {"source": "sentence-transformers/all-MiniLM-L6-v2", ...},
    "v2": {"source": "shibing624/text2vec-base-chinese", ...},
}
# python index.py → V2, python index.py --v1 → V1
```

### 8.2 对比测试

| 问题 | V1（英文模型） | V2（中文模型） |
|------|------|------|
| "多店支持是怎么实现的" | ❌ 来源全是无关文档 | ✅ 四文件全部分析（config/crawler/db/main） |
| "介绍一下你的知识库" | ✅ 准确 | ✅ 准确 |
| "crawler.py 反检测做了什么" | ⚠️ 答案对，来源错误引用 RAG 文档 | ✅ 答案对，来源引用知识文档 |
| 检索速度 | 快（79MB 模型） | 可接受（400MB 模型，首次加载慢） |

### 8.3 V2 新增问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `sentence-transformers` 安装失败 | 网络问题导致 pip 不完整安装 | 重试 |
| 模型 400MB 下载可能占 C 盘 | HuggingFace 默认缓存路径 | `set HF_HOME=E:\...` 重定向到 E 盘 |
| V1/V2 代码重复 | 每版本复制一份 | 重构为多模型统一架构 |
| chroma_db 有两个目录 | 旧代码路径不统一 | 合并到 chroma_db/，用 collection 区分 |

### 8.4 架构改进

```
V1:  每个版本一套独立代码  → 文件冗余，对比不方便
V2:  共用扫描/切段/存库逻辑 → MODELS 注册表切换模型
     chroma_db 统一目录    → V1/V2 不同 collection
     --v1 参数一键对比      → 同一问题两个模型结果并排看
```

### 8.5 答案质量之外的结构改进

除了中文检索更准，V2 比 V1 多了三个工程层面的提升：

| 改进 | V1 | V2 |
|------|------|------|
| 多版本管理 | 每版本一套独立代码，改一行要改两份 | MODELS 注册表统一管理，加新模型 5 行 |
| 一键对比 | 无法对比 | `--v1` 参数同时跑两模型看结果差异 |
| 目录结构 | `chroma_db` + `chroma_db_v2` 两个目录 | 合并到一个目录，collection 区分版本 |

**核心：检索质量靠模型，代码质量靠架构。** V2 两个都做了。

### 8.6 项目筛选器（2026年7月12日）

**需求：** 知识库覆盖 6 个项目，问代码问题时需要限定搜索范围，避免搜到无关项目。

**实现：** 聊天界面顶部加项目按钮（日报/RFM/视频/直播/培训/知识库 + 全部）。点选后 URL 带 `?project=pos_daily_report` 参数。

```python
# rag_engine.py — 检索后按路径过滤
def ask(question, project_filter=""):
    results = query(question)
    if project_filter:
        results = [(d, m) for d, m in results if project_filter in m["source"]]
```

**效果：**
- 点"日报"问"数据库表结构" → 只搜 pos_daily_report 的代码和文档
- 点"RFM"问同一问题 → 搜不到日报的表结构，返回 rfm_report 相关内容
- 点"全部" → 跨项目搜索

前端改动：chat.html 加 `.project-bar` 导航条 + CSS。后端改动：server.py 传参 + rag_engine.py 过滤。共约 20 行代码。

### 8.7 V2 结论

**中文模型替换 + 多模型统一架构 = V2 完成。** 检索质量从"基本不可用"提升到"能精准回答中文技术问题"。加 V3 只需在 MODELS 里加 5 行。

---

## 九、V3 计划（已完成 ✅）

| 升级 | 状态 | 说明 |
|------|:--:|------|
| 增量索引 | ✅ | 文件指纹对比，只更新变动文件 |
| 对话历史 | ✅ | IP 会话记忆，支持追问 |
| 来源去重 | ✅ | set 去重合并显示 |
| 项目筛选器 | ✅ | 6 项目按钮，限定搜索范围 |
| 导师模式 prompt | ✅ | 展开讲解：是什么→为什么→在项目哪里→怎么实现 |

## 十、V4 计划（待实施）

| 升级 | 优先级 | 说明 |
|------|:--:|------|
| 千问 Qwen3-Embedding | P1 | 面试前换，精度更高，面试加分 |
| 领域分类 | P2 | metadata 标签区分技术/业务/求职 |
| 自动待办 | P2 | 对话结束生成待验证事项 |
| 企微机器人接入 | P2 | 手机微信直接问 |
| 代码结构理解 | P3 | 理解 import 关系，分析模块依赖 |

---

## 十一、逐行讲解模式开发记录（2026年7月12日）

### 11.1 需求演进

```
V1 需求：导师模式 — 选文件 → 全文发给 DeepSeek → 讲解
  ↓ 用户反馈："我希望左边代码右边讲解，逐行对齐"
V2 需求：左右分栏 — 代码 + 讲解对齐，书签收藏，追问追加
  ↓ 用户反馈："选中行只能一行一行选，应该支持 Shift 范围选"
  ↓ 用户反馈："点发送没反应"、"full 选项看不到"
  ↓ 用户反馈："讲解面板显示文件不存在"
V3 需求：Shift/Ctrl 多选 + 书签 + 独立按钮 + 路径编码修复
```

### 11.2 踩坑全记录

| # | 问题 | 原因 | 解决 | 耗时 |
|:--:|------|------|------|:--:|
| 1 | 选中代码行无视觉反馈 | CSS `background:#1e293b` 跟默认 `#0f172a` 太接近 | 改为 `background:#312e81`（紫色）+ 白色文字 | 5min |
| 2 | 点"发送"讲解无反应 | 下拉菜单 `<select>` + 单按钮的交互容易出错 | 改为三个独立按钮：讲解选中 / 全文讲解 / 收藏 | 10min |
| 3 | 讲解面板显示"文件不存在" | Windows 路径 `E:\Trae` 的 `\T` 被 JavaScript 当成转义符，路径变成 `E:Trae` | 服务端用 `json.dumps(filepath)` 编码，前端用 `{{ filepath_json\|safe }}` 接收 | 15min |
| 4 | 代码行只能单击单选 | 没有键盘修饰符支持 | 加 Shift+click（范围选）、Ctrl+click（加减选） | 10min |
| 5 | 书签按钮不存在 | 第一版忘了加 | 底部栏加 `🔖 收藏` 按钮，localStorage 存储 | 5min |
| 6 | 导师模式文件列表点文件名不跳转 | `<label>` 里嵌套链接，点击 label 触发的是勾选 | 文件名单独加 `<a href="/code-tutor?...">逐行学→</a>` | 5min |
| 7 | Jinja2 没有 `urlencode` 过滤器 | Jinja2 内置过滤器不含 URL 编码 | 服务端 `jinja_env.filters["urlencode"] = quote` | 2min |
| 8 | `FULL_CODE` 在无文件时未定义导致 JS 报错 | 无 filepath 时 `code_json=[]`，JS 访问空数组正常但页面空白 | 无文件时渲染文件列表而非空代码栏 | 5min |
| 9 | `const FILE = ;` 空值，代码面板白屏 | 旧服务器进程占着 8002 端口没杀干净，一直在跑旧代码（旧版本没有 `filepath_json` 变量） | `netstat -ano \| findstr :8002` 找到 PID → `taskkill /F /PID xxx` → 重启 | 10min |

### 11.3 技术关键点

**路径编码：** Windows 反斜杠在 JSON/JS 中是转义符，必须用 `json.dumps()` 编码才能在 `<script>` 标签里安全使用。

**localStorage 书签：** 纯前端实现，存 `{file, project, lines, code, note, date}`。跨会话持久化，点书签跳回原文原行。

**Shift 范围选：** 记录 `lastClicked` 行号，Shift+点击时从 `lastClicked` 到当前行全选。

### 11.4 效果

```
导师模式选文件 → 跳转逐行讲解页
左栏代码（行号可点）→ Shift 范围选 / Ctrl 加减选
右栏 DeepSeek 讲解（按 L行号 | 内容 格式输出）
底部：讲解选中 | 全文讲解 | 收藏 | 追问输入
书签面板：localStorage 持久化，点书签跳回原文件原行
```

### 11.5 调试技巧："让错误自己说话"

排查"点按钮没反应"最费时间的不是修 bug——是**不知道 bug 是什么**。

```javascript
// 之前：失败静默
} catch(e) {
    pane.innerHTML = '请求失败';
}

// 之后：把原因和上下文全打到界面上
} catch(e) {
    pane.innerHTML = `❌ ${e.message}<br><small>文件: ${FILE}</small>`;
}
```

看到"文件不存在: E:Trae CNAI..."立刻就知道是路径反斜杠被 JavaScript 吃了。比翻浏览器控制台快得多。

**原则：凡是用户能看到的地方出错了，把错误直接展示在界面上，不要吞掉。**

---

## 十二、V3.2 阅读模式开发（2026年7月13日）

### 12.1 需求

用户希望有一个"阅读模式"——不是逐行等 DeepSeek 实时回答，而是事前生成好讲解，打开即时阅读。需要目录跳转、代码联动、笔记标注、追问面板。

### 12.2 核心设计

**预生成讲解：** `generate_explanation.py` 调 DeepSeek 一次性生成结构化 JSON（技术栈/大纲/函数/逐行），存到 `.explanations/` 目录。阅读模式直接读 JSON，秒开。

**行号精准方案：** 代码每行加 `L行号:` 前缀发给 DeepSeek，AI 直接引用不自己数。经验证行号准确率从"经常偏"提升到"完全准确"。

**双向联动：** 点目录项跳代码行，点代码行跳讲解区，纯前端 scrollIntoView 实现。

**笔记系统：** 页内弹窗（非 browser prompt）→ 标签+内容+代码上下文 → localStorage 持久化 → 侧边栏搜索/展开/删除。

### 12.3 踩坑

| # | 问题 | 原因 | 解决 |
|:--:|------|------|------|
| 10 | 行号不准 | AI 自己数行号，空行/docstring 容易错 | 代码加 L行号 前缀，AI 直接引用 |
| 11 | 同名 .py 覆盖 | config.py 在多个项目都存在 | 文件名加项目前缀 `pos_daily_report_config.py.json` |
| 12 | 测试文件漏掉 | 只扫了项目根目录 | tests/ 目录往上再取一层 |
| 13 | `</script>` 重复 | 模板编辑时多了一个闭合标签 | 全文搜索删除重复标签 |
| 14 | 旧笔记格式炸 JS | V3.1 笔记是对象 `{}`，V3.2 是数组 `[]` | loadNotes() 检测类型，不兼容则清空 |
| 15 | 语义模糊问题搜不到 | "最底层毫无依赖"太抽象 | 用户适应具体问法，知识库加 FAQ |
| 16 | `prompt()` 弹窗太小 | 浏览器原生弹窗不支持大段文字 | 自定义页内弹窗（textarea + 字数统计） |
| 17 | 文件冲突生成覆盖 | generate 脚本没处理 tests/ 路径 | 父目录+子目录双级前缀 |

### 12.4 效果

```
4 个项目 × 36 个预生成讲解 JSON
每个文件打开即时阅读，无需等待 DeepSeek
技术栈标签 + 大纲目录 + 函数总览 + 逐行讲解
左右联动 + 可编辑笔记 + 追问面板
文档模式：27 篇 TO DO 知识文档一键阅读
```

### 12.5 V3.2 结论

**预生成讲解 + 阅读模式 = 从"等 AI 回答"到"即时翻阅"。** 36 个文件覆盖 4 个项目，行号准确，笔记系统完善。三个模式（搜索/导师/文档）统一入口。

---

## 十三、V3.3 力导向图改进（2026年7月14日）

### 13.1 需求

用户反馈四个问题：
1. 项目文件依赖图悬停节点不显示技术栈
2. 从阅读模式点"← 返回"直接跳到顶层总览，而不是回到该项目依赖图
3. 灰色节点（category 2，配置文件等）点进去没有预生成讲解
4. JS 文件也需要生成讲解

### 13.2 改动清单

| 文件 | 改动 |
|------|------|
| `server.py` GRAPH_DATA | 36 个节点全部加 `tech` 字段；rfm_report 补 charts.js/config.js/rfm.js 三个缺失节点；补全 echarts.min.js/chat.html/reader.html/notebook.html 的空 `file` 路径 |
| `templates/chat.html` | `goBack()` 直接调 `showMain()`；`showProject()` 深拷贝节点防污染原数据；初始化去掉 sessionStorage 回退，`/` 永远显示总览；顶层图和项目图统一 tooltip 格式 |
| `templates/reader.html` | 返回链接从 `<a href="/">` 改为 `<a href="/?project={{ project }}">`，配合 URL 参数恢复项目依赖图 |
| `generate_explanation.py` | 按扩展名自适应 prompt（.py/.js/.html/.css/.yaml/.json/.md/.txt 八种），非代码文件跳过 functions 字段 |

### 13.3 踩坑

| # | 问题 | 原因 | 解决 | 耗时 |
|:--:|------|------|------|:--:|
| 18 | `goBack()` 点"返回总览"始终跳回项目图 | 函数逻辑反了——查到 `drillProj` 存在就调 `showProject(proj)`，死循环在项目视图 | 改为直接 `showMain()`，清除 sessionStorage | 5min |
| 19 | 首页 `/` 显示 knowledge-assistant 依赖图而非总览 | init 逻辑在 URL 无参数时 fallback 到 sessionStorage，旧值残留 | 去掉 sessionStorage 回退，`/` 永远显示总览；URL 参数 `?project=` 来自 reader 返回链接，才是正确的恢复入口 | 10min |
| 20 | `window.open` 打开 reader 但 sessionStorage 不共享 | 新标签页有独立 sessionStorage，`drillProj` 在原标签页 | reader 返回链接显式传 `?project=` 参数，不再依赖 sessionStorage | 5min |
| 21 | Edit 工具反复报"String to replace not found" | 文件用 tab 缩进？空格？换行 `\r\n` vs `\n`？实际是 2-space 缩进 + `\n`，但工具传入的字符串缩进不匹配 | 用 Python `assert old in content` 精确验证后再 replace，每条必过断言 | 15min |
| 22 | 代码改完但页面不生效 | 旧 Python 进程占着 8002 端口，`pkill` 杀不掉 Windows 进程 | `netstat -ano | grep 8002` 找到 PID → `taskkill /F /PID xxx` 强杀 → 重启 | 10min |
| 23 | `p.data.tech` 在项目依赖图 tooltip 不显示 | 不是 tooltip 写错，是根本进不去项目依赖图（bug #18 和 #19 导致无法正常下钻），测试全在错误视图里兜圈 | 先修导航 bug，tech tooltip 自然生效 | 连带修复 |
| 24 | `showProject()` 的 `forEach` 直接改原 ARCH_DATA 节点 | 第一次进项目图正常，多次进出后节点对象的 symbolSize/itemStyle/label 被反复覆写 | 改为 `data.nodes.map()` 浅拷贝每个节点再设置样式，不污染原数据 | 5min |

### 13.4 技术关键点

**深拷贝 vs 原数据污染：** showProject 之前用 `data.nodes.forEach(function(n) { n.symbolSize = ... })` 直接在 GRAPH_DATA 原对象上改属性。多次进出不同项目图后，原数据被反复篡改。改为 `var nodes = data.nodes.map(function(n) { var copy = {}; for (var k in n) copy[k] = n[k]; ...; return copy; })` 每次生成全新副本。

**sessionStorage 的双面性：** 同一个标签页内 sessionStorage 方便恢复状态，但新标签页（`window.open`）有独立存储。跨页面状态传递必须走 URL 参数，不能依赖 sessionStorage。

**进程残留的排查链：** `pkill -f python` → 不管用 → `netstat -ano | grep 8002` → 找到 PID → `taskkill /F /PID xxx` → 确认端口释放 → 重启。Windows 上杀进程不能只靠名字匹配。

### 13.5 效果验证

```
全部项目总览：6 节点悬停显示技术栈 ✓
项目依赖图：36 节点悬停显示技术栈 ✓
reader 返回：带 ?project= 参数 → 回到该项目依赖图 ✓
返回总览：清除 sessionStorage → 顶层总览 ✓
灰色节点：全部可点击进入阅读模式 ✓
JS 讲解：generate_explanation.py 支持 8 种格式 ✓
```

---

## 十四、V3.3+ 计划

| 升级 | 说明 |
|------|------|
| 千问 Qwen3-Embedding | 面试前换，面试加分 |
| 移动端 PWA | 手机保存到桌面，像 App 一样用 |
| MD 文件渲染 | 文档模式支持 Markdown 格式渲染 |
| 内网培训项目补进 GRAPH_DATA | 目前 5/6 项目有依赖图，差一个 |

---

> 📅 实验日期：2026年7月12-14日
> 📌 最终结论：**RAG 搜碎片，导师读全文，阅读翻预生成——三模式互补，覆盖所有学习场景。**
> 💡 最大教训：行号让 AI 自己数是靠不住的。给数据打标签比期待 AI 聪明更可靠。
> 📌 V1→V2 核心结论：**中文模型是检索质量跃升的关键，多模型统一架构是可持续迭代的基础。**
> 💡 最大的坑：不要假设 API 存在，不要硬编码路径到 C 盘，不要让历史代码污染当前目录。
> 🔧 V3.3 新教训：**sessionStorage 不跨标签页，跨页面状态传递靠 URL 参数；Windows 杀进程不能只靠 pkill；先确认导航链路通畅再测功能，否则全在错误视图里白测。**

---

## 十五、V3.3 代码清理（2026年7月14日）

| # | 问题 | 处理 |
|:--:|------|------|
| 25 | `server.py` 顶部 `import os`，中间又 `import os as _os`，全文只用 `_os.` | 统一用 `os.`，删掉别名行 |
| 26 | 两个路由内各自 `import json as _json`，顶部已有 `import json` | 路由内删掉，复用顶部 json |
| 27 | `v1-archive/` 旧版代码存档，已无引用 | 删除目录 |
| 28 | `test.txt` / `test_v2.txt` 早期 RAG 测试输出，非测试用例 | 删除 |
| 29 | `.chroma-cache` `.chroma-real` `.model-cache` 三个空目录 | 删除 |
| 30 | `/tutor/explain` 路由渲染已删除的 `tutor.html`，导师模式提交即报错 | 改为渲染 `chat.html` |
