# Demand Mining —— 用 lastdays 引擎挖掘真实用户需求

> 研究 brief + 落地方案。2026-06-08。状态:设计,待实现。

## 判断(先行)

**可行,而且 lastdays 是少数合适的底座。** 需求挖掘工具的头号死因是平台 API 封锁/涨价——最有名的 GummySearch 2025-11 因拿不到 Reddit Data API 商业 license 关闭。lastdays 的 **keyless 多源**架构天然抗这个单点失败(一个源死了还有十个)。

但**不能直接复用现在的"话题相关性引擎"**。实测:用现引擎搜信号词 `"I wish there was"` 在 Bluesky 召回 24 条,全是噪声(`wish everyone a happy donut day`、`I wish there was a rapture but for assholes`)——只命中字面词,没有"需求语义"。所以核心改造 = 在多源抓取之上加一层**需求信号识别 + 语义聚类 + 机会打分**。

---

## Part 1 · 研究 Brief

### A. 数据源(按信号质量分层)

**T1 — 高信号(明确求工具 / feature request,最可行动):**
- **GitHub Issues**(`label:feature-request`、`enhancement`)——最结构化的需求,已有 github 源,改搜 issues 即可。
- **Stack Overflow**(`is there a way/library to …` = 工具 gap)——已有 SO 源。
- **Reddit 求助/吐槽 sub**:r/SomebodyMakeThis、r/AppIdeas、r/Lightbulb、r/SaaS、r/Entrepreneur + 各垂直 sub。Reddit 数据中心 IP 403 → 用 **Lemmy** 补 + agent WebSearch `site:reddit.com`。
- **Hacker News**:`Ask HN: is there a…`、`Ask HN: how do you…`(重复问=痛点)、Show HN 反映的 gap——已有。

**T2 — 实时吐槽 / wish:**
- **Bluesky**(实时 pain/wish,有真实 engagement)——已有。
- **Lemmy**(Reddit 替代社区)——已有。

**T3 — 产品反馈(需新接入,feature-request 金矿):**
- **App Store / Google Play 评论**(差评里的"要是能…"、缺失功能)——iTunes RSS `customerreviews` 是 keyless 的,强候选新源。
- **G2 / Capterra / Product Hunt 评论**(对竞品的不满 = 直接机会;"X 很好但缺 Y")。
- 垂直:IndieHackers、各 SaaS 社区、Discourse 论坛。

> 覆盖原则:同一需求被**多个独立源 + 多个独立作者**提到 = 真实度高;单源单人 = 噪声/回音室。

### B. 信号识别(关键:句式模式 > 单个词)

直接用单词("wish")会召回海量噪声。要用**结构化句式 pattern**:

- **直接求工具**(最强可行动):`is there a (tool|app|way|service|library) (that|to) …` / `I wish there was a (tool|app) …` / `does anyone know (a|of a) … that` / `looking for (a|an) … to` / `why is(n't) there a …` / `someone should build` / `somebody make this`
- **痛点 + 强度**:`I hate that` / `so frustrating` / `tired of` / `wasting hours on` / `pain in the ass`,强度放大词 `every single time` / `killing me` / `desperate`
- **付费意愿(最强信号)**:`I'd pay for` / `would happily pay` / `take my money` / `willing to pay $`
- **workaround(需求强但无产品)**:`my workaround is` / `I built a script/spreadsheet to` / `hacky solution`
- **feature request(对现有产品)**:`feature request` / `please add` / `it would be great if` / `missing feature`

**反信号(去噪,同等重要):**
- **已被解答** → 回复里有 `use X` / `try Y` / `X does exactly this` → 需求已满足,降权/丢弃。
- **纯情绪无诉求** → rant 但说不出"要什么"。
- **字面命中但语义无关**(实测的 "happy donut day")→ 必须语义层过滤。
- **自推/广告** → `I built X, check it out`(除非是验证需求的 workaround)。
- **太泛/哲学** → 不可行动。

> 引擎做**规则粗筛**(必须含需求句式 pattern + 排除已解答),agent 做**语义细判**(这是不是真的产品需求)。轻量混合,延续 lastdays 哲学。

### C. 去噪 / 去重 / 聚类

- **去噪**:反信号规则(engine)→ 语义判断(agent)。
- **去重 / 聚类**:同一需求的多次表达聚成一个"需求簇"。
  - engine 层:关键词/CJK-bigram 相似度粗聚(stdlib,无第三方 embedding)。
  - agent 层:语义聚类(LLM 读信号帖,归并同义需求)——主力,符合零依赖。
  - **频次 = 验证强度**:N 个独立帖 / N 个源 / N 个作者表达同一需求 = 真实。
- **root need ≠ stated request**:用户说"想要 X 功能",真实需求常是底层 JTBD。agent 抽 Job-to-be-Done,而非照搬用户提的解法。

### D. 机会打分(Opportunity Score)

借 **Ulwick "Opportunity Scoring"**(JTBD):`Opportunity = Importance × (1 − Satisfaction)`。映射到信号:

| 维度 | 怎么算 |
|------|--------|
| **强度 Importance** | 信号类型权重(付费 > wish/求工具 > 痛点 > 提问)× 情感强度 |
| **广度/频次** | 独立帖数 × 独立源数 × 独立作者数(去回音室后) |
| **未满足 (1−Satisfaction)** | 回复里无现成解=高;有人抱怨现有工具烂=中;已被解答=低 |
| **趋势/新鲜** | 复用现有 recency;窗口内是否上升 |
| **付费信号** | 有明确付费意愿 → 强加权 |

**输出 = 机会清单**,每条:需求一句话 + JTBD + 机会分 + 现有方案 gap + 频次/源数 + 证据帖(链接 + 原话引用)。

---

## Part 2 · 落地方案(复用 lastdays)

**复用(不动骨架):** 多源 keyless 并行抓取、窗口、TTL 缓存、tier 降级、engagement、render→agent 的轻量混合。

**新增 / 改造:**

1. **新 mode / skill**:`demandmine "<领域>"`(领域可宽 `developer tools` 或窄 `note-taking apps`)。复用 engine,换"识别层"。
2. **信号查询扩展**:engine 把 `领域 × SIGNAL_PHRASES` 组合成多查询,或对全文源搜信号短语 + 领域过滤。各源定制:GitHub→`label:enhancement`、SO→`is there a 领域`、Bluesky/Lemmy/HN→领域+信号词。
3. **`lib/demand.py`(新)**:`demand_score(text) -> (score, signal_type)` —— 句式 pattern 正则 + 强度词 + 付费检测 + 反信号扣分。item 保留条件从 `is_on_topic` 换成 `demand_score > 阈值 AND 命中领域`。
4. **`score.py` 加 demand 维度**:机会分 = 强度 × 频次 × 未满足 × recency。
5. **render `DEMAND SIGNALS` 块**:输出信号帖(带 demand 分、信号类型、源、作者)给 agent。
6. **agent 层(SKILL)**:读信号帖 → 语义聚类成需求簇 → 抽 JTBD → Opportunity 打分 → 输出去重排序的机会清单(带证据)。

**MVP(第一版)范围:**
- 复用现有源:GitHub Issues + SO + HN + Bluesky + Lemmy + Reddit(WebSearch 兜底)。
- `lib/demand.py` 信号识别(正则 pattern + 反信号)+ 离线单测。
- 新 SKILL `demandmine`:engine 抓信号帖 → agent 聚类+打分+机会清单。
- **不做**(fast-follow):App Store 评论源、自动 embedding 聚类(agent 代劳)、付费墙竞品评论。

---

## 风险与诚实标注

- **信号召回噪声大**(已实测)→ engine 只粗筛,语义判断必须 agent 兜底,别指望纯正则。
- **频次 ≠ 真实需求**:回音室 / 同人多发 → 按独立作者 + 独立源去重。
- **幸存者/人群偏差**:能爬到的是"爱发帖人群"(开发者、英文社区偏多)的需求,不代表全市场。中文需求要靠 B站/(stub 的)微博知乎,目前弱。
- **已解答需求**要过滤,否则会把"已存在的产品"当机会推荐。
- **ToS/合规**:公开数据 + keyless + 不转售原文,风险低于 GummySearch 的 Reddit-API 转售模式;但仍应尊重各源 robots/ToS,控频。
- **这是信号发现,不是市场调研**:机会清单是"值得深挖的假设",不是"被验证的需求"——下一步仍需人工/访谈验证。
