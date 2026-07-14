#!/bin/bash
cd "E:/Trae CN/AI-Kart-Live/knowledge-assistant"
git add -A
git commit -m "v3.3: 力导向图改进 + 讲解生成多语言 + 6项目完整依赖图"
git tag -a v3.3 -m "V3.3 - 力导向图交互改进：技术栈悬停、返回导航修复、深度拷贝、8种格式讲解、6项目完整依赖图（48节点）"
git push origin v3.2 --tags
echo "=== DONE ==="
