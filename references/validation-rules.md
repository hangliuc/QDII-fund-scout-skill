# 数据自校验规则

> 本文档列出 `validate.py` 实现的所有校验规则。回答的是"为什么数据有时不全 / 不对，怎么自动发现？"

## 校验分四层

```
┌──────────────────────────────────────────────────────┐
│ L1 Schema    │ 字段在不在、类型对不对                │
├──────────────────────────────────────────────────────┤
│ L2 Range     │ 字段值在不在合理区间                  │
├──────────────────────────────────────────────────────┤
│ L3 Consistency │ 同一基金内多个字段间逻辑是否自洽    │
├──────────────────────────────────────────────────────┤
│ L4 Cross-source │ 不同接口返回的同一字段是否一致    │
└──────────────────────────────────────────────────────┘
```

每层独立运行，结果合并到 `_validation` 字段。

## L1 · Schema 校验

按 profile 区分必填字段集合：

| profile | 必填字段 |
|---------|---------|
| `quick` | `code`, `name`, `nav`, `return_1y`, `purchase_status` |
| `compare` | `code`, `name`, `scale`, `return_1y`, `purchase_status`, `total_fee` |
| `detail` | `code`, `name`, `scale`, `nav`, `nav_date`, `purchase_status`, `mgmt_fee`, `custody_fee`, `total_fee`, `manager_name`, `top10_holdings` |
| `qdii` | `code`, `name`, `scale`, `return_1y`, `purchase_status`, `market_distribution` |

字段缺失 → `fatal`（致命错误）；字段存在但为空字符串 / null → 同样视为缺失。

### 顶层校验

- `update_date` 必须存在，否则 warning

## L2 · Range 校验

### 数值字段范围

| 字段 | 合理区间 | 越界处理 |
|------|---------|---------|
| `scale`（亿） | `0 ~ 10000` | fatal |
| `nav` | `0.1 ~ 50` | warning |
| `return_1w` | `-100 ~ 500` | warning |
| `return_1m` | `-100 ~ 500` | warning |
| `return_3m` | `-100 ~ 500` | warning |
| `return_6m` | `-100 ~ 500` | warning |
| `return_1y` | `-100 ~ 500` | fatal |
| `return_3y` | `-100 ~ 500` | fatal |
| `return_ytd` | `-100 ~ 500` | warning |
| `return_since_inception` | `-100 ~ 500` | warning |
| `mgmt_fee` | `0 ~ 5` | fatal |
| `custody_fee` | `0 ~ 5` | fatal |
| `service_fee` | `0 ~ 5` | warning |
| `total_fee` | `0 ~ 5` | fatal |
| `tracking_error` | `0 ~ 30` | warning |
| `drawdown_1y` | `0 ~ 90` | warning |
| `manager_tenure` | `0 ~ 30` | warning |
| `manager_return` | `-100 ~ 500` | warning |

### 字符串字段格式

| 字段 | 正则 | 说明 |
|------|------|------|
| `code` | `^\d{6}$` | 6位数字，不匹配 → fatal |
| `update_date` | `^\d{4}-\d{2}-\d{2}$` |  |
| `nav_date` | `^\d{4}-\d{2}-\d{2}$` | 格式不匹配 → warning |
| `purchase_status` | `^(开放|限大额|限小额|暂停|未知|暂停(限大额)|暂停(限小额))$` | 非标准值 → warning |

## L3 · Consistency 校验

### 费率合计自洽

```python
mgmt = _to_float(entry.get("mgmt_fee"))
custody = _to_float(entry.get("custody_fee"))
service = _to_float(entry.get("service_fee"))
total = _to_float(entry.get("total_fee"))

if mgmt is not None and custody is not None and service is not None and total is not None:
    expected = round(mgmt + custody + service, 4)
    if abs(expected - total) > 0.02:
        violation("费率合计", f"total_fee={total} != mgmt+custody+service={expected}")
```

容差 0.02%（浮点精度 + 四舍五入），超过即告警。

### C 类基金 service_fee 校验

```python
if "C" in name and (service is None or service == 0):
    violation("费率/C类", "C类基金应有 service_fee")
```

C 类基金名称中包含「C」，必须存在非零的 service_fee。

### 持仓自洽

```python
top10 = entry.get("top10_holdings") or []
if top10:
    pcts = [_to_float(s.get("pct")) for s in top10]
    pcts = [p for p in pcts if p is not None]
    if pcts:
        total = sum(pcts)
        if total > 100.5:
            violation("持仓/合计", f"前十大占比合计 {total:.2f}% > 100%")
        if 0 < total < 5:
            violation("持仓/合计", f"前十大占比合计 {total:.2f}% 异常低")
        if any(p > 50 for p in pcts):
            violation("持仓/单只过大", "单只持仓 > 50%")

    codes = [s.get("code") for s in top10 if s.get("code")]
    if len(codes) != len(set(codes)):
        violation("持仓/重复", f"top10 代码有重复 {codes}")
```

### 市场分布自洽

```python
dist = entry.get("market_distribution") or {}
country_items = {k: v for k, v in dist.items() if not str(k).startswith("_")}
if country_items:
    total = sum(_to_float(v) or 0 for v in country_items.values())
    if total > 105:
        violation("市场分布/合计", f"国家占比合计 {total:.2f}% > 100%", fatal=True)
    if 0 < total < 30:
        violation("市场分布/合计", f"国家占比合计 {total:.2f}% 过低，可能漏抓")
```

- 合计 > 105% → fatal（一定有解析错误）
- 合计 < 30% → warning（可能漏抓了国家行）
- 以 `_` 开头的键（如 `_source`、`_total_pct`、`_inferred`）不参与合计计算

### 申购状态自洽（参考规则）

以下规则来自 fund-data-fetching skill 的校验规范，可在后续版本中补充到 validate.py：

```python
status = entry["purchase_status"]
limit = entry["purchase_limit"]
eff_closed = entry.get("effectively_closed", False)

if status == "开放" and limit not in ("无限制", ""):
    violation("开放状态不应有 purchase_limit")

if status == "暂停" and not eff_closed:
    violation("暂停申购必须 effectively_closed=True")

if status == "限小额" and "元" not in str(limit):
    violation("限小额的单位应是元而非万")

if status == "限大额" and "万" not in str(limit):
    violation("限大额的单位应是万")

if "元" in str(limit):
    amt = float(re.search(r'([\d.]+)', limit).group(1))
    if amt <= 1000 and not eff_closed:
        violation("元单位且≤1000应 effectively_closed=True")
```

### 持仓季度自洽（参考规则）

```python
quarters = [q["quarter"] for q in entry.get("holdings", [])]

if len(quarters) != len(set(quarters)):
    violation(f"持仓季度有重复: {quarters}")

parsed = [(int(re.match(r'(\d{4})年(\d)季度', q).group(1)),
           int(re.match(r'(\d{4})年(\d)季度', q).group(2)))
          for q in quarters]
if parsed != sorted(parsed, reverse=True):
    violation(f"持仓季度未按时间倒序: {quarters}")
```

## L4 · Cross-source 校验

### 规模：主页 vs 档案

```python
home_scale = _to_float(entry.get("_home_scale"))
arch_scale = _to_float(entry.get("_arch_scale"))
if home_scale and arch_scale:
    pct_diff = abs(home_scale - arch_scale) / max(home_scale, arch_scale)
    if pct_diff > 0.20:
        violation("scale 多源差异", f"主页={home_scale} 档案={arch_scale} 差={pct_diff:.1%}")
```

容差 20%（主页和档案页更新节奏不同），超过即 warning。

### 收益率：排行接口 vs 主页

```python
rank = _to_float(entry.get("_rank_return_1y"))
home = _to_float(entry.get("_home_return_1y") or entry.get("return_1y"))
if rank is not None and home is not None:
    diff = abs(rank - home)
    if diff > 1.0:
        violation("return_1y 多源差异", f"排行={rank} 主页={home} 差={diff:.2f}")
```

容差 1pp（净值更新时间差），超过即 warning。

### 经理：主页 vs 经理页（参考规则）

```python
home_mgr = entry.get("_home_manager")
mgr_page_current = entry.get("current_tenure", {}).get("managers", [])
if home_mgr and mgr_page_current and home_mgr not in mgr_page_current:
    violation(f"主页经理 {home_mgr} 不在经理页 current 列表 {mgr_page_current}")
```

### 持仓占比 vs 资产净值（参考规则）

```python
top10_sum = sum(pct_to_float(s["pct"]) for s in top10)
disclosed_stock_pct = entry.get("_disclosed_stock_pct")
if disclosed_stock_pct and top10_sum > disclosed_stock_pct + 5:
    violation(f"top10 占比 {top10_sum}% 超过披露的股票总占比 {disclosed_stock_pct}%")
```

## 输出结构

```jsonc
{
  "_validation": {
    "schema": "ok|incomplete",
    "schema_missing": ["basic.scale", ...],
    "range_violations": [
      {"code": "012870", "field": "return_1y", "value": 350, "rule": "-100 ~ 500"}
    ],
    "consistency_violations": [
      {"code": "012870", "rule": "费率合计", "msg": "total_fee=1.5 != mgmt+custody+service=1.8"}
    ],
    "cross_source_violations": [
      {"code": "012870", "field": "return_1y", "rank": 42.18, "home": 38.50, "diff": 3.68}
    ],
    "fatal_count": 0,
    "warning_count": 3
  }
}
```

## 用法

### Python API

```python
from validate import validate_data, validate_fund_entry, print_report, ValidationError

result = validate_data(data, profile="compare")

if result.fatal_count > 0:
    print("❌ 存在致命错误，data.json 不应使用：")
    for f in result.fatal:
        print(f"  - {f}")
    raise ValidationError("数据校验未通过")

if result.warning_count > 0:
    print(f"⚠ {result.warning_count} 条警告（非阻塞）：")
    for w in result.warnings:
        print(f"  - {w}")

data["_validation"] = result.to_dict()
```

### CLI

```bash
python scripts/core/validate.py data.json compare
python scripts/core/validate.py data.json qdii
```

### 单条校验

```python
result = validate_fund_entry(entry, profile="detail")
```

## 校验结果判定

| 情况 | 处理 |
|------|------|
| `fatal_count > 0` | 数据不可用，必须修复后重新抓取 |
| `warning_count > 0` 且 `fatal_count == 0` | 数据可用，但需关注告警项 |
| 两者均为 0 | 数据通过全部校验 |

## Profile 与校验严格度

| Profile | Schema 必填数 | 典型场景 |
|---------|-------------|---------|
| `quick` | 5 | 快速筛选，只看核心指标 |
| `compare` | 6 | 批量对比，需要费率和规模 |
| `detail` | 11 | 完整详情，所有关键字段 |
| `qdii` | 6 | QDII 专项，必须有市场分布 |

Profile 越严格，Schema 缺失越容易触发 fatal。选择 Profile 时应根据实际使用场景，不要对所有数据都用 `detail`。
