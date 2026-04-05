# 部署和调度操作文档

## 环境要求
- Python 3.7+
- pip 包管理器
- Git CLI（用于GitHub Pages发布）
- 必要的环境变量配置：
  - `GITHUB_TOKEN`: GitHub访问令牌，用于发布到GitHub Pages
  - `INOREADER_CLIENT_ID`（可选）：Inoreader API客户端ID
  - `INOREADER_CLIENT_SECRET`（可选）：Inoreader API客户端密钥
  - `ADMIN_PASSWORD`（可选）：后台管理密码，默认`admin123`

## 安装依赖
```bash
pip install -r requirements.txt
```

## 手动执行
### 增量更新（默认，推荐用于定时调度）
```bash
# 仅抓取最近2小时的新闻，速度快
./sync.sh

# 或者直接调用Python脚本
python main.py
```

### 全量更新
```bash
# 抓取最近24小时的新闻，用于首次部署或定期全量同步
./sync.sh --full

# 或者直接调用Python脚本
python main.py --full
```

### 测试模式（只抓取不处理）
```bash
python main.py --test
```

### 不发布到GitHub Pages
```bash
python main.py --no-publish
```

## 定时调度配置（Openclaw）
### 调度配置示例
```yaml
# Openclaw 任务配置
name: x-reader-news-sync
schedule: "0 * * * *"  # 每小时整点执行
command: "/path/to/x-reader/sync.sh"
environment:
  GITHUB_TOKEN: "your-github-token"
  ADMIN_PASSWORD: "your-admin-password"
```

### 调度说明
- 建议每小时执行一次，保证新闻时效性
- 每天凌晨可执行一次全量更新，确保数据完整性
- 执行超时建议设置为10分钟

## 后台管理
### 启动后台服务
```bash
python src/web/app.py
```
访问地址：http://localhost:8081/admin
默认密码：`admin123`（可通过`ADMIN_PASSWORD`环境变量修改）

### 后台功能
- 📰 新闻列表查看、搜索、多维度筛选
  - 支持领域、热度、时间、评级4种筛选维度
  - 支持点击表头排序（热度、发布时间、来源数，可切换升降序）
  - 筛选和排序支持组合使用，分页时参数自动保持
- 🔥 时代情绪热点管理
- 📡 RSS源管理（增删改查、启用禁用、权重设置）
- 📊 系统状态查看
- ⚙️ 配置管理
- ✏️ 新闻评分修正和反馈

## 目录结构说明
```
x-reader/
├── sync.sh                 # 同步执行脚本
├── main.py                 # 主程序入口
├── src/                    # 源代码目录
│   ├── fetchers/           # 数据抓取模块
│   ├── processors/         # 数据处理模块
│   ├── publishers/         # 发布模块
│   ├── models/             # 数据模型
│   ├── data/               # 数据存储模块
│   ├── web/                # 后台Web服务
│   └── utils/              # 工具函数
├── data/                   # 数据存储目录
│   ├── sources/            # RSS源配置
│   ├── feedback/           # 用户反馈数据
│   └── news_data.json      # 最终新闻数据
├── logs/                   # 同步日志目录
├── docs/                   # 文档目录
└── requirements.txt        # 依赖列表
```

## 常见问题排查
### 1. 同步失败
- 检查日志文件`logs/sync_*.log`查看具体错误信息
- 确认环境变量配置正确
- 检查网络连接是否正常，是否能访问数据源和GitHub

### 2. 后台无法访问
- 检查8081端口是否被占用
- 确认Python依赖已经正确安装
- 查看后台服务的启动日志

### 3. 新闻更新不及时
- 检查定时调度是否正常运行
- 确认数据源访问正常
- 查看同步日志是否有错误信息

### 4. 已处理ID太多
- 系统会自动保留最近10000条已处理ID，约7天的量，无需手动清理
- 如需重置，可删除`.processed_ids.json`文件
