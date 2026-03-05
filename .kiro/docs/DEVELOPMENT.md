# 开发环境配置指南

## 🚀 快速开始

### 一键启动

```bash
# macOS / Linux
./dev.sh

# Windows
dev.bat
```

### 手动启动

#### 后端
```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 前端
```bash
cd frontend
npm install
npm run dev
```

**访问地址：**
- 前端: http://localhost:5173
- 后端: http://localhost:8000
- API文档: http://localhost:8000/docs

---

## 📦 生产环境部署

```bash
# 构建镜像
docker build -t knowledgemap:latest .

# 运行容器
docker run -p 7860:7860 \
  -v $(pwd)/backend/data:/app/backend/data \
  -e MODELSCOPE_API_KEY=your_key \
  knowledgemap:latest
```

---

## 🔧 环境变量

创建 `.env` 文件：
```env
MODELSCOPE_API_KEY=your_api_key_here
```

---

## 🐛 常见问题

### 前端无法连接后端API

- 检查 `frontend/vite.config.ts` 中的 proxy 配置
- 确保后端运行在 `http://localhost:8000`

### 后端修改不生效

- 确认 uvicorn 使用了 `--reload` 参数
- 检查终端日志是否有重载提示

### 前端修改不生效

- 检查 Vite 终端是否有 HMR 更新日志
- 尝试 `rm -rf frontend/node_modules/.vite && npm run dev`

---

## 📝 开发工作流

### 修改后端代码
1. 编辑 `backend/*.py` 文件并保存
2. uvicorn 自动检测变化并重载
3. 刷新浏览器测试

### 修改前端代码
1. 编辑 `frontend/src/**/*.vue` 或 `.ts` 文件并保存
2. Vite HMR 自动更新浏览器，无需手动刷新

---

## 📚 相关文档

- [FastAPI](https://fastapi.tiangolo.com/)
- [Vite](https://vitejs.dev/)
- [Vue 3](https://vuejs.org/)
