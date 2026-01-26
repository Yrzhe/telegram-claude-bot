---
name: akshare-stocks
description: 股票数据查询技能，支持A股、港股、美股的实时行情、历史K线、财务指标查询。当用户询问股票价格、行情、PE/PB/ROE等估值指标、财务数据、K线数据时使用此技能。
---

# AKShare 股票数据查询技能

使用 AKShare 库获取股票市场数据，支持 A股、港股、美股。

## 使用场景

- 用户询问某只股票的实时价格/行情
- 用户需要查看历史 K 线数据（日/周/月）
- 用户询问估值指标：PE（市盈率）、PB（市净率）、PS（市销率）
- 用户需要财务数据：ROE、ROA、营收、净利润、毛利率
- 用户想要股东户数、机构持仓等信息
- 用户需要对比多只股票的数据

## 重要提示

1. **需要先创建 Python 脚本**：由于没有 Bash 权限，你需要将 Python 代码写入文件
2. **告知用户执行方式**：让用户使用 /run 命令执行脚本，或通过其他方式运行
3. **数据保存**：将查询结果保存为 CSV 或 Markdown 文件，方便用户查看

## A股数据查询

### 实时行情（东方财富）
```python
import akshare as ak
import pandas as pd

# 获取 A 股实时行情（全部）
df = ak.stock_zh_a_spot_em()
# 字段：代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 最高, 最低, 今开, 昨收, 量比, 换手率, 市盈率-动态, 市净率, 总市值, 流通市值, 60日涨跌幅, 年初至今涨跌幅

# 查询特定股票
stock_code = "600519"  # 贵州茅台
stock_info = df[df['代码'] == stock_code]
print(stock_info)
```

### 历史 K 线数据
```python
import akshare as ak

# 日 K 线（前复权）
df = ak.stock_zh_a_hist(
    symbol="600519",      # 股票代码
    period="daily",       # daily/weekly/monthly
    start_date="20240101",
    end_date="20241231",
    adjust="qfq"          # qfq前复权, hfq后复权, ""不复权
)
# 字段：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
```

### 个股财务指标
```python
import akshare as ak

# 财务分析指标（ROE、ROA等）
df = ak.stock_financial_analysis_indicator(
    symbol="600519",
    start_year="2023"
)
# 包含：净资产收益率(ROE), 总资产收益率(ROA), 毛利率, 净利率等

# 主要财务指标
df = ak.stock_financial_abstract_ths(
    symbol="600519",
    indicator="按年度"  # 或 "按报告期"
)
# 包含：营业收入, 净利润, 每股收益, 每股净资产等
```

### 估值指标
```python
import akshare as ak

# 从实时行情获取 PE、PB
df = ak.stock_zh_a_spot_em()
stock = df[df['代码'] == "600519"][['代码', '名称', '最新价', '市盈率-动态', '市净率', '总市值', '流通市值']]

# 历史估值数据
df = ak.stock_a_lg_indicator(symbol="600519")
# 字段：trade_date, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_mv
```

### 股东户数
```python
import akshare as ak

# 股东户数变化
df = ak.stock_zh_a_gdhs(symbol="600519")
# 字段：股东户数统计截止日, 股东户数, 较上期变化, 人均流通股, 股价, 人均持股金额
```

## 港股数据查询

### 实时行情
```python
import akshare as ak

# 港股实时行情（全部）
df = ak.stock_hk_spot_em()
# 字段：代码, 名称, 最新价, 涨跌额, 涨跌幅, 今开, 最高, 最低, 昨收, 成交量, 成交额

# 查询特定股票
stock = df[df['代码'] == "00700"]  # 腾讯控股
```

### 历史 K 线
```python
import akshare as ak

# 港股历史数据
df = ak.stock_hk_hist(
    symbol="00700",       # 港股代码
    period="daily",       # daily/weekly/monthly
    start_date="20240101",
    end_date="20241231",
    adjust="qfq"
)
```

## 美股数据查询

### 实时行情
```python
import akshare as ak

# 美股实时行情
df = ak.stock_us_spot_em()
# 字段：序号, 名称, 最新价, 涨跌额, 涨跌幅, 今开, 最高, 最低, 昨收, 总市值, 市盈率, 代码

# 查询特定股票（使用股票名称或代码）
stock = df[df['代码'].str.contains('AAPL')]  # 苹果
stock = df[df['代码'].str.contains('NVDA')]  # 英伟达
stock = df[df['代码'].str.contains('TSLA')]  # 特斯拉
```

### 历史 K 线
```python
import akshare as ak

# 美股历史数据
df = ak.stock_us_hist(
    symbol="105.AAPL",    # 纳斯达克用105., 纽交所用106.
    period="daily",
    start_date="20240101",
    end_date="20241231",
    adjust="qfq"
)
```

### 美股常用代码前缀
- 纳斯达克：105.AAPL, 105.NVDA, 105.TSLA, 105.GOOGL, 105.AMZN, 105.META
- 纽约证交所：106.JPM, 106.V, 106.JNJ

## 执行步骤

1. **确定用户需求**：股票代码、市场（A股/港股/美股）、数据类型
2. **编写查询脚本**：创建 Python 脚本文件（如 `stock_query.py`）
3. **保存查询结果**：将数据保存为 CSV 或 Markdown 格式
4. **发送给用户**：使用 send_telegram_file 发送结果文件

## 输出格式示例

### Markdown 报告格式
```markdown
# 股票分析报告：贵州茅台（600519）

## 基本行情
| 指标 | 数值 |
|------|------|
| 最新价 | 1680.00 |
| 涨跌幅 | +2.35% |
| 成交额 | 45.6亿 |

## 估值指标
| 指标 | 数值 |
|------|------|
| PE (动态) | 28.5 |
| PB | 8.2 |
| 总市值 | 2.1万亿 |

## 财务指标
| 指标 | 2024Q3 |
|------|--------|
| ROE | 31.5% |
| 净利率 | 52.3% |
| 营收增速 | 15.2% |
```

## 注意事项

1. **网络延迟**：AKShare 从网络获取数据，可能需要几秒钟
2. **数据时效**：实时行情有约15分钟延迟，非实时交易数据
3. **代码格式**：
   - A股：6位数字（如 600519, 000001）
   - 港股：5位数字（如 00700, 09988）
   - 美股：需要加交易所前缀（105.AAPL, 106.JPM）
4. **交易时间**：非交易时间查询的是上一交易日数据
5. **错误处理**：代码不存在或网络问题时会报错，需要做好异常处理

## 常用股票代码速查

### A股热门
- 600519 贵州茅台
- 000001 平安银行
- 600036 招商银行
- 000858 五粮液
- 601318 中国平安
- 600900 长江电力

### 港股热门
- 00700 腾讯控股
- 09988 阿里巴巴-SW
- 03690 美团-W
- 09618 京东集团-SW
- 00941 中国移动

### 美股热门
- 105.AAPL 苹果
- 105.NVDA 英伟达
- 105.TSLA 特斯拉
- 105.GOOGL 谷歌
- 105.AMZN 亚马逊
- 105.META Meta
- 105.MSFT 微软
