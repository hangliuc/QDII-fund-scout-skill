# QDII-fund-scout

QDII 基金数据查询工具。一键查看你持有的 QDII 基金的**申购限额、收益率、费率、回撤**等关键数据，支持推送到飞书或企业微信群。

> **目标用户**：持有 QDII 基金但不想每天挨个打开 App 查限额的投资者。
>
> **解决的问题**：QDII 基金限购频繁变动，今天还能买明天可能就暂停了。这个工具帮你一键查清所有持仓基金的状态。

---

## 快速开始（零基础友好）

### 第一步：安装

打开终端（Mac 的"终端"App 或 Windows 的 PowerShell），运行：

```bash
# 下载工具
git clone git@github.com:hangliuc/QDII-fund-scout-skill.git
cd QDII-fund-scout-skill

# 一键安装（自动装依赖、生成配置文件）
bash setup.sh
```

安装过程中会：
- 自动检测 Python 环境
- 自动安装依赖包
- 询问是否配置飞书/企业微信推送（可选，直接回车可跳过）
- 验证安装是否成功

> **如果 git clone 报错**：可以直接从 GitHub 页面下载 ZIP 压缩包，解压后进入文件夹运行 `bash setup.sh`

### 第二步：运行

安装完成后，每次想查询基金数据时：

```bash
bash run.sh
```

然后会看到一个菜单界面，用数字键选择操作即可：

```
  1) 查看我的基金（使用配置文件）
  2) 手动输入基金代码查询
  3) 查询后推送到飞书
  4) 查询后推送到企业微信
  ...
  8) 打开可视化界面（浏览器配置）
  0) 退出
```

> **首次使用**：先选 **6) 编辑我的基金列表**，输入你持有的基金代码和名称，保存后再选 **1) 查看我的基金**。

或者选 **8) 打开可视化界面**，浏览器中会打开一个图形化页面，直接点击按钮操作，无需记忆任何命令。

---

## 常见 QDII 基金代码参考

完整名单（727 只，含分类）保存在 `references/qdii_fund_list.json`，由天天基金网实时数据生成。下文仅列出部分热门基金供快速参考：

| 代码 | 基金名称 | 类型 |
|------|---------|------|
| 017437 | 华宝纳斯达克精选 | QDII-普通股票 |
| 014002 | 浦银安盛全球智能科技 | QDII-普通股票 |
| 021277 | 广发全球精选 | QDII-普通股票 |
| 017731 | 嘉实全球产业升级 | QDII-普通股票 |
| 000043 | 嘉实美国成长 | QDII-普通股票 |
| 161128 | 易方达标普信息科技 | 指数型-海外股票 |
| 012922 | 易方达全球成长精选 | QDII-普通股票 |
| 021842 | 国富全球科技 | QDII-普通股票 |
| 539002 | 建信新兴市场混合 | QDII-普通股票 |
| 015202 | 汇添富全球移动互联 | QDII-普通股票 |
| 024239 | 华夏全球科技先锋 | QDII-普通股票 |
| 016702 | 银华海外数字经济 | QDII-普通股票 |
| 018036 | 长城全球新能源车 | QDII-普通股票 |
| 017145 | 华宝海外新能源汽车 | QDII-普通股票 |
| 017204 | 华宝海外科技 | QDII-普通股票 |
| 008254 | 华宝致远混合 | QDII-普通股票 |
| 017093 | 景顺长城纳斯达克科技 | QDII-普通股票 |
| 016665 | 天弘全球高端制造 | QDII-普通股票 |
| 002891 | 华夏移动互联 | QDII-普通股票 |

> 完整列表见 `references/qdii_fund_list.json`（727 只，覆盖所有 QDII 类型）
>
> 可在 UI 中直接搜索：运行 `bash run.sh` → 选 **8) 打开可视化界面** → 下拉选择基金

---

## 配置推送渠道（飞书 / 企业微信）

推送功能让你在手机端也能看到数据，无需打开电脑。**非必需，不配置也能用。**

### 飞书配置

1. 打开飞书 App → 进入任意一个群聊
2. 点击群设置（右上角 ...）→ **群机器人** → **添加机器人**
3. 搜索 **Webhook 机器人** → 添加
4. 复制 Webhook 地址（以 `https://open.feishu.cn/open-apis/bot/v2/hook/` 开头）
5. 运行 `bash run.sh` → 选 **7) 配置推送渠道** → 粘贴地址

### 企业微信配置

1. 打开企业微信 App → 进入任意一个群聊
2. 点击群设置 → **群机器人** → **添加机器人**
3. 创建一个新机器人 → 复制 Webhook 地址（以 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=` 开头）
4. 运行 `bash run.sh` → 选 **7) 配置推送渠道** → 粘贴地址

---

## 数据说明

### 查询结果中的字段含义

| 字段 | 说明 | 示例 |
|------|------|------|
| 基金名称 + 代码 | 基金唯一标识 | 易方达纳指100C 012870 |
| 近 1 年收益率 | 过去一年的收益表现，**红色 = 涨，绿色 = 跌** | +29.61% |
| 申购状态 | 当前能否买入 | 开放 / 限大额 / 限小额 / **暂停** |
| 限额 | 每日最多能买多少钱 | 1000元 / 10万元 / 无限制 |
| 总费率 | 管理费 + 托管费 + 销售服务费 | 0.80% |

### 申购状态说明

QDII 基金额度有限，经常会出现限购或暂停申购，这是正常现象：

| 状态 | 含义 | 能否买入 |
|------|------|---------|
| 开放申购 | 正常买入，无限制 | 可以 |
| 限大额 | 单日购买有上限（通常几万到百万） | 小额可买 |
| 限小额 | 单日限购金额很小（几百到几千元） | 可买但额度极少 |
| 暂停申购 | 完全不能买入 | 不可买 |

### 自动数据校验

工具从天天基金（主）和好买基金（备用）两个来源获取数据，自动对比：

- 两源数据一致 → 无标记，直接展示
- 申购状态不一致 → 自动取**更严格**的状态（保护用户不会误以为能买）
- 数值字段小差异 → 自动信任主源数据
- 仅重大异常 → 标记 ⚠ 提示

---

## 高级用法（命令行）

对于熟悉命令行的用户，可以直接使用 CLI 命令：

```bash
cd QDII-fund-scout-skill/scripts

# 查看单只基金详情
python3 cli.py detail 012870

# 批量对比多只基金
python3 cli.py compare 012870,006479,008971

# 推送到飞书
python3 cli.py compare 012870,006479 --push feishu

# 推送到企业微信
python3 cli.py compare 012870,006479 --push wechat

# 同时推送到飞书和微信
python3 cli.py compare 012870,006479 --push feishu,wechat

# JSON 格式输出（方便程序处理）
python3 cli.py compare 012870,006479 --format json

# CSV 格式输出（可用 Excel 打开）
python3 cli.py compare 012870,006479 --format csv
```

### 使用配置文件

```bash
# 用配置文件中的基金列表
python3 cli.py compare --config ~/.fund-scout/config.json
```

### Python API 调用

```python
import sys
sys.path.insert(0, "QDII-fund-scout/scripts")

from core.fetcher import FundFetcher
from adapters.feishu import FeishuAdapter

fetcher = FundFetcher(rate_limit=0.5)
result = fetcher.compare(["012870", "006479"])

adapter = FeishuAdapter(webhook_url="https://open.feishu.cn/...")
adapter.send(result)

# 查看仲裁详情
for fund in result.funds:
    if fund._cross_validation:
        print(f"⚠ {fund.name}: {fund._cross_validation}")
    if fund._cross_resolved:
        print(f"ℹ️ {fund.name}: 已自动仲裁 {fund._cross_resolved}")
```

---

## 数据来源

| 数据 | 来源 | 方式 |
|------|------|------|
| 净值 / 收益 / 规模 / 类型 | 天天基金（主） / 好买基金（备） | HTML 解析 |
| 费率 / 跟踪标的 | 天天基金档案页 | HTML 解析 |
| 申购限额 / 状态 | 天天基金（主） / 好买基金（备） | HTML 解析（正则） |
| NAV 历史 / 回撤 | 天天基金 API | JSONP → JSON |
| 基金经理 | 天天基金经理页 | HTML 解析 |
| 前十大持仓 | 天天基金持仓页 | HTML 解析 |
| 市场 / 行业分布 | 证监会季报 PDF | pdfplumber |

> **主备切换**：天天基金不可用时自动切换到好买基金，两者都失败返回"数据暂不可用"，不会崩溃。
>
> **自动仲裁**：两源数据差异时，申购状态取更严格值（暂停 > 限小额 > 限大额 > 开放），数值字段信任主源，仅有重大异常时才标记 ⚠。

---

## 定时自动化

配合 SOLO Schedule 或 GitHub Actions 可以每天早上自动查询并推送到群里：

```yaml
# .github/workflows/qdii-daily.yml
on:
  schedule:
    - cron: '0 1 * * 1-5'  # 工作日 09:00 CST
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install requests pdfplumber
      - run: python3 scripts/cli.py compare --push feishu
        env:
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
```

---

## 常见问题

### Q: 运行报 `command not found: python3`？

A: 需要安装 Python 3。下载地址：[python.org](https://www.python.org/downloads/)，安装后重新运行即可。

### Q: 查询结果中有基金显示"数据暂不可用"？

A: 说明天天基金和好买基金都无法获取该基金的数据，可能是网络问题或该基金代码有误，请稍后重试。

### Q: 如何删除已配置的基金？

A: 运行 `bash run.sh` → 选 **6) 编辑我的基金列表** → 直接输入新的列表覆盖

### Q: 查询需要多久？

A: 每只基金约需 5-10 秒（含请求间隔），5 只基金大约 30-60 秒。这是为了防止被网站封禁，故意设置的慢速请求。

### Q: 推送消息中出现 ℹ️ 和 ⚠ 标记？

A: ℹ️ 表示数据来自两个来源且已自动仲裁，数据可信。⚠ 表示发现重大数据异常，建议核实。

---

## 项目结构

```
QDII-fund-scout/
├── setup.sh                 # 一键安装脚本（从这里开始）
├── run.sh                   # 一键运行脚本（交互菜单 + 可视化界面）
├── SKILL.md                 # Agent 入口（TRAE / SOLO 用）
├── ui/
│   ├── server.py            # 可视化界面后端服务
│   └── index.html           # 可视化界面前端页面
├── scripts/
│   ├── cli.py               # 命令行入口
│   ├── core/
│   │   ├── fetcher.py       # 请求调度器（主备切换 + 自动仲裁）
│   │   ├── models.py        # 数据模型
│   │   ├── validate.py      # 4 层校验
│   │   └── sources/
│   │       ├── base.py       # 数据源基类
│   │       ├── eastmoney.py # 天天基金数据源（主）
│   │       ├── howbuy.py    # 好买基金数据源（备）
│   │       └── csrc.py      # 证监会数据源
│   ├── formatters/          # JSON / CSV / Markdown 输出
│   └── adapters/            # 飞书 / 微信推送
└── references/
    ├── qdii_fund_list.json               # 全量 QDII 基金列表（727 只，自动生成）
    ├── nasdaq_passive_qdii_c_funds.json  # 纳斯达克被动 C 类基金参考列表
    ├── config.example.json  # 配置示例
    ├── data-sources.md      # 数据源 URL 速查
    ├── field-glossary.md    # 字段语义与陷阱
    ├── validation-rules.md  # 校验规则
    └── compliance.md        # 合规指南
```

---

## License

MIT

## Disclaimer

数据来源公开渠道，仅供学习研究参考，不构成任何投资建议。历史业绩不代表未来表现。禁止商业数据转售。
