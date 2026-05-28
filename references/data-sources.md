# 数据源完整说明

本文档详细列出 fund-scout 用到的所有数据源、URL 模板、字段映射与已知陷阱。SKILL.md 只列高频项，长尾内容看这里。

## 数据源分级

| 级别 | 来源 | 权威性 | 用途 |
|------|------|--------|------|
| 一级（最权威） | 证监会基金披露网站 `eid.csrc.gov.cn` | 法定披露原文 | 季报市场分布、行业分布、十大重仓 |
| 二级（高时效） | 天天基金 `fund.eastmoney.com` | 商业平台 | 主页、规模、收益率、净值、申购状态 |
| 二级（备份） | 天天基金 F10 档案 `fundf10.eastmoney.com` | 商业平台 | 费率、经理、跟踪误差、十大重仓（汇总版） |
| 三级（衍生） | 排行接口 `rankhandler.aspx` | 商业平台 | 批量收益率（一次拿全市场） |

> 涉及到法定披露字段（市场分布、行业配置、官方持仓），**必须用一级源**。天天基金的「区域分布」字段会根据持仓股名做粗暴推断，错误率高。

## 字段 ↔ 数据源对应表

### 基金主页 `http://fund.eastmoney.com/{code}.html`

可抓到的字段：

| 字段 | 选择器 / 正则 | 备注 |
|------|--------------|------|
| `name` | `<title>(.*?)\((\d{6})\)` | 含全名+代码 |
| `type` | infoOfFund 块 `类型[：:]\s*([^\s|]+)` | 如「股票指数」、「股票型」 |
| `risk` | `\|\s*([^\s]+风险)` | 「中高风险」 |
| `scale` | `规模\s*[：:]\s*([\d.,]+亿元)` | 单位：亿元；和档案页交叉对比 |
| `manager_name` | `基金经理[：:]\s*([\u4e00-\u9fa5A-Za-z]+)` | 当前经理（仅名字） |
| `found_date` | `成\s*立\s*日\s*[：:]\s*([\d-]+)` | YYYY-MM-DD |
| `company` | `管\s*理\s*人\s*[：:]\s*([\u4e00-\u9fa5]+)` | 基金公司全称 |
| `nav` | `class="fix_dwjz[^"]*"[^>]*>([\d.]+)` | 单位净值 |
| `nav_date` | `class="fix_date">\((\d{2}-\d{2})` | MM-DD（无年份） |
| `return_1m` 等 | `近1月[：:]\s*</span>\s*<span[^>]*>([-\d.]+)%?` | 百分比字符串 |
| `purchase_status` 系列 | 见 SKILL.md「申购状态四态校验」 | 必须四态完整 |

### 基金档案 `http://fundf10.eastmoney.com/jbgk_{code}.html`

| 字段 | 正则 | 备注 |
|------|------|------|
| `mgmt_fee` | `管理费率.*?([\d.]+)%` | 单位：% |
| `custody_fee` | `托管费率.*?([\d.]+)%` |  |
| `service_fee` | `销售服务费率.*?([\d.]+)%` | C 类必有 |
| `benchmark` | `跟踪标的.*?<td[^>]*>(.*?)</td>` | 用 strip_tags 清洗 |
| `scale` | `资产规模.*?([\d.,]+)\s*亿` | 比主页更新慢但更稳 |

### 基金经理 `http://fundf10.eastmoney.com/jjjl_{code}.html`

> 这是经理头像 / 任期 / 回报 / 简历的**唯一可靠源**。主页 manager 字段可能缺失。

| 字段 | 提取方式 | 备注 |
|------|---------|------|
| `tenures` | 第一个 `<table class="...jloff...">`，每行 5 列 | 历任 + 当前 |
| `current_tenure` | `tenures` 中 `end == "至今"` 的那条 | 当前在任 |
| `avatar` | `<div class="...pic..."> img src` | 注意补 `https:` 前缀 |
| `profiles` | `<div class="jl_intro">` 块 | 含姓名 / 上任日期 / 简历 |

### 季度持仓 `http://fundf10.eastmoney.com/FundArchivesDatas.aspx`

```
?type=jjcc&code={code}&topline=10&year={year}&month=&rt=0.1
```

返回 JSONP，需要先正则取 `content:"..."`，反转义后再解析 HTML：

```python
m = re.search(r'content:"(.+?)",arryear:', text, re.DOTALL)
content = m.group(1).replace('\\"', '"').replace('\\/', '/')
```

注意：

- `topline=10` 拿前10大；要拿前20改成 20
- 同一只基金在 year=2026 / 2025 接口里可能都返回 2025Q4，需按 `quarter` 字段去重
- 字段顺序：[序号, 代码, 名称(<a>), 涨跌幅, 占比, 持股数, 持仓市值]
- 港股代码非纯数字（如 `00700`），用 `raw[0].isdigit()` 判定行有效会失败 → 见 `field-glossary.md`

### NAV 历史 `https://api.fund.eastmoney.com/f10/lsjz`

```
?callback=jQuery&fundCode={code}&pageIndex={page}&pageSize=20&startDate={start}&endDate={end}
```

⚠ **关键陷阱**：`pageSize` 实际无效，每页固定 20 条。计算回撤必须分页拿全。

返回结构：

```jsonc
{
  "Data": {
    "LSJZList": [
      {"FSRQ": "2026-05-21", "DWJZ": "1.2345", "JZZZL": "0.5"}
    ],
    "FundType": "0", "TotalCount": 244
  }
}
```

回撤计算：

```python
all_navs.sort(key=lambda x: x[0])
peak = all_navs[0][1]
max_dd = 0
for _, nav in all_navs:
    if nav > peak: peak = nav
    dd = (peak - nav) / peak
    if dd > max_dd: max_dd = dd
```

### 排行接口 `http://fund.eastmoney.com/data/rankhandler.aspx`

```
?op=ph&dt=kf&ft=zs&rs=&gs=0&sc=1nzf&st=desc
&sd={start}&ed={end}&qdii=&tabSubtype=,,,,,
&pi={page}&pn=2000&dx=1&v=0.{rand}
```

参数：

- `ft=zs` 指数型，`ft=gp` 股票型，`ft=hh` 混合，`ft=qdii` QDII。批量抓时建议遍历 `ft` 取并集。
- `sc=1nzf` 按近1年排序，`sd=...&ed=...` 限制时间窗口
- 返回 `datas:["code,abbr,name,date,nav,acc,...,r1m,r3m,r6m,r1y,...,r3y,rytd,rsl"]`，列顺序固定，但**不同 ft 列数偶有差异**，至少要校验 `len(fields) >= 16`

### 证监会季报披露 `eid.csrc.gov.cn`

#### 搜索接口

```
GET http://eid.csrc.gov.cn/fund/disclose/advanced_search_report.do
?aoData=<URL编码的JSON>
```

aoData 关键字段：

| name | value | 说明 |
|------|-------|------|
| `reportType` | `FB030` | 季报；半年报 `FB020`，年报 `FB010` |
| `reportYear` | `"2026"` | 字符串 |
| `fundCode` | `"012920"` | 主代码（A 类） |
| `fundShortName` | `"易方达全球成长精选"` | 备用搜索词 |
| `iDisplayLength` | `20` | 返回条数 |

返回 `aaData[]`，每项含 `uploadInfoId`（即 instance id）、`reportName`、`fundShortName` 等。

#### PDF 下载

```
http://eid.csrc.gov.cn/fund/disclose/instance_show_pdf_id.do?instanceid={uploadInfoId}
```

返回 PDF 二进制。用 pdfplumber 解析。

## 已知陷阱汇总

### NAV 接口

- **pageSize 无效**：无论传什么值，每页固定返回 20 条。计算回撤时必须分页遍历拿全量数据。
- **Data: null**：`lsjz` API 经常返回 `Data: null`，需要重试。
- **JSONP 包裹**：返回值被 `jQuery...(...)` 包裹，需先剥离回调函数名再解析 JSON。

### 港股代码识别

- 港股代码为 5 位数字（如 `00700`），与 A 股 6 位数字不同。
- 少数港股带字母后缀（如 `BABA-SW`、`9988-SW`），`isdigit()` 判定会失败。
- 代码实现中用 `raw[0].isdigit()` 判断行有效性，港股序号行正常但代码字段格式不同，需注意不要误过滤。

### 季报同季跨年重复

- 同一只基金在 `year=2026` 和 `year=2025` 接口里可能都返回 `2025年4季度` 的数据。
- 必须按 `quarter` 文本去重，避免持仓数据重复。

### CSRC 搜索

- C 类、ETF 联接基金不直接披露季报，用 C 类代码搜不到 → 必须用 A 类主代码（`main_code`）搜索。
- 搜索失败时可用基金简称（`short_name`）作为备用搜索词。
- `advanced_search_report.do` 偶尔返回 502，重试通常能解决。
- PDF 下载较慢（5-15s），timeout 必须设到 ≥ 30s。

### 占位符与格式

- 百分号有半角 `%` 和全角 `％` 两种，解析时需统一。
- 持股数千分位可能是 `,` 也可能是中文 `，`。
- NA 占位：偶尔返回 `--` 或 `-`，应解析为 0 或 null。

## 反爬基本盘

### 通用规则

| 规则 | 说明 |
|------|------|
| User-Agent | 用真实浏览器 UA，禁止 `python-requests/2.x` |
| Referer | 天天基金一律 `http://fund.eastmoney.com/`，CSRC 一律 `http://eid.csrc.gov.cn/fund/disclose/advanced_search.html` |
| 限速 | 每次请求随机 sleep 0.5~2.0s，关键接口 1.0~2.0s |
| 禁止并发 | 所有请求必须串行，禁止多线程/协程并发 |
| 重试 | HTTP 200 但内容为空 → 视为失败，重试一次后放弃 |
| 连续失败熔断 | 连续 30 次失败自动停止 |

### 天天基金特有

- 单 IP 连续请求超过 ~50 次会被临时封 5~10 分钟，表现为返回登录页
- `lsjz` API 经常返回 `Data: null`，需要重试
- 排行接口在交易日 9:00-15:30 偶尔不返回，建议盘后跑

### CSRC 特有

- `advanced_search_report.do` 偶尔返回 502，重试通常能解决
- PDF 下载较慢（5-15s），timeout 必须设到 ≥ 30s
- 部分基金（C 类、ETF 联接）不直接披露季报，用主代码搜不到 → 试基金简称

### 请求头模板

天天基金：

```python
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "http://fund.eastmoney.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
```

证监会：

```python
CSRC_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer": "http://eid.csrc.gov.cn/fund/disclose/advanced_search.html",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
```
