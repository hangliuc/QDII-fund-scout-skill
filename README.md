# QDII-fund-scout

QDII 基金数据获取工具。从天天基金、证监会基金披露网站等公开渠道抓取 QDII 基金的核心数据：**申购限额、收益率、回撤、费率、季度持仓、市场投资分布**。

## Features

- **QDII 专项**：申购状态四态校验（开放 / 限大额 / 限小额 / 暂停），自动标记实质暂停（限额 ≤ 1000 元/天）
- **多源数据**：天天基金（主页 + 档案 + 经理 + NAV 历史）+ 证监会季报 PDF（市场/行业分布）
- **收益率排行**：按近 1 年收益率从高到低排列
- **一站式推送**：支持飞书卡片（Grid 布局 + 红涨绿跌）、企业微信 Markdown
- **多格式输出**：JSON / CSV / Markdown
- **数据校验**：4 层校验（Schema → 范围 → 一致性 → 跨源），QDII 专项 profile
- **零硬编码**：基金代码通过搜索或 config.json 传入，遵守 robots.txt
- **可集成**：Python API + CLI + 配置文件，配合 SOLO Schedule / GitHub Actions 实现定时自动化

## Quick Start

```bash
git clone https://github.com/hangliuc/lh-xiaohongshu.git
cd lh-xiaohongshu/QDII-fund-scout/scripts

# 单只基金详情
python3 cli.py detail 012870

# 批量对比（限额 + 收益率）
python3 cli.py compare 012870,006479,008971

# 搜索纳斯达克 100 基金
python3 cli.py search "纳斯达克100" --type 指数型 --class C

# 推送到飞书
python3 cli.py compare 012870,006479 --push feishu

# JSON 格式输出
python3 cli.py compare 012870,006479 --format json
```

## Requirements

Python 3.9+，依赖：

```
requests
pdfplumber（证监会季报 PDF 解析）
```

```bash
pip install requests pdfplumber
```

## Data Sources

| 数据 | 来源 | 方式 |
|------|------|------|
| 净值 / 收益 / 规模 / 类型 | 天天基金主页 | HTML 解析 |
| 费率 / 跟踪标的 | 天天基金档案页 | HTML 解析 |
| 申购限额 / 状态 | 天天基金主页 | HTML 解析（正则） |
| NAV 历史 / 回撤 | 天天基金 API | JSONP → JSON |
| 基金经理 | 天天基金经理页 | HTML 解析 |
| 前十大持仓 | 天天基金持仓页 | HTML 解析 |
| 市场 / 行业分布 | 证监会季报 PDF | pdfplumber |

## Configuration

配置文件 `~/.fund-scout/config.json`：

```json
{
  "my_funds": [
    {"code": "012870", "name": "易方达纳指100C"}
  ],
  "push": {
    "feishu_webhook": "",
    "wechat_webhook": ""
  }
}
```

使用配置文件：

```bash
python3 cli.py compare --config ~/.fund-scout/config.json
```

## Push to Feishu / WeChat

```bash
# 飞书
python3 cli.py compare 012870,006479 --push feishu

# 企业微信
python3 cli.py compare 012870,006479 --push wechat

# 同时推送
python3 cli.py compare 012870,006479 --push feishu,wechat
```

环境变量方式（不写死在代码里）：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

## Python API

```python
import sys
sys.path.insert(0, "QDII-fund-scout/scripts")

from core.fetcher import FundFetcher
from adapters.feishu import FeishuAdapter

fetcher = FundFetcher()
result = fetcher.compare(["012870", "006479"])

adapter = FeishuAdapter(webhook_url="https://open.feishu.cn/...")
adapter.send(result)
```

## Automation

配合 GitHub Actions 定时推送：

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
      - run: python3 QDII-fund-scout/scripts/cli.py compare --push feishu
        env:
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
```

## Project Structure

```
QDII-fund-scout/
├── SKILL.md                  # Agent 入口（aegnt skills spec）
├── scripts/
│   ├── cli.py                # CLI 入口
│   ├── core/
│   │   ├── fetcher.py        # 请求调度器
│   │   ├── models.py         # 数据模型
│   │   ├── validate.py       # 4 层校验
│   │   └── sources/
│   │       ├── eastmoney.py  # 天天基金数据源
│   │       └── csrc.py       # 证监会数据源
│   ├── formatters/           # JSON / CSV / Markdown
│   └── adapters/             # 飞书 / 微信推送
└── references/
    ├── data-sources.md       # 数据源 URL 速查
    ├── field-glossary.md     # 字段语义与陷阱
    ├── validation-rules.md   # 校验规则
    └── compliance.md         # 合规指南
```

## License

MIT

## Disclaimer

数据来源公开渠道，仅供学习研究参考，不构成任何投资建议。历史业绩不代表未来表现。禁止商业数据转售。
