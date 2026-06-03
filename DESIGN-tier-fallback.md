# PLAN — 统一 tier 降级框架(firecrawl × gpt-researcher 借鉴)

> 五阶段法的 PLAN 产物。RESEARCH 已完成;此为实现蓝图,EXECUTION 按它落地,REVIEW 用它当验收基线。

## 背景(为什么)

研究了三个标杆:
- **firecrawl** `scrapeURL`:14 个抓取 engine 按 `quality` 分数排成 `fallbackList` 依次降级;负 quality = 特种/兜底 engine;per-domain 专用 engine(wikipedia/x-twitter);retryTracker 防无限降级。
- **gpt-researcher** `multi_agents`:researcher→reviewer→reviser 循环,reviewer 按 guidelines 判"够好/需改";质量分级思想。
- **官方 anthropics/skills**:frontmatter 极简,渐进式指令。

**现状痛点**(上轮实测发现):lastdays 的源各自手写降级——Reddit 是 `.json`(有互动数)→ `RSS`(无互动数)硬编码 try/except;B站也有 primary/fallback。降级后**质量天花板被限死且无人知情**:Reddit RSS 无 upvotes → 排序退化成几乎只看时间 → `r/flashlight "Flea market find"` 这种噪音(标题偶然含 "market")挤进结果。

**目标**:把"多 tier 降级 + 质量分级 + 降级感知"抽象成 registry 的统一能力(firecrawl 的 engine-fallback 思想),并让降级 tier 自动触发相关性过滤 + 诚实标注(gpt-researcher 的质量门思想)。顺手治好 Reddit RSS 噪音。

## 设计原则

1. **向后兼容**:现有 `fetch(query, window, *, env, depth)` 接口不变。单 fetch 源自动视为"单 tier、quality=正常、非降级"。
2. **零依赖**:纯 stdlib,不引第三方(与项目一贯原则一致)。
3. **诚实**:降级(无互动数)的 item 必须可识别,并在 evidence/JSON 标注,排序时不伪造。

## 改动点(文件级)

### 1. `lib/registry.py` — 新增 Tier 概念
```python
@dataclass(frozen=True)
class Tier:
    fetch: Callable          # fetch(query, window, *, env, depth) -> list[Item]
    quality: int = 100       # 越高越先试;负数=兜底(firecrawl 约定)
    degraded: bool = False   # True=该 tier 拿不到完整信号(如无 engagement)
    label: str = ""          # "json" / "rss" — 进 metadata.tier 便于诊断

@dataclass(frozen=True)
class Source:
    name: str
    lang: str
    fetch: Callable = None          # 旧式单 fetch(保留,向后兼容)
    tiers: tuple[Tier, ...] = ()    # 新式多 tier;给了 tiers 就忽略 fetch
    requires_key: bool = False
    implemented: bool = True
    aliases: tuple = field(default_factory=tuple)

    def ordered_tiers(self) -> list[Tier]:
        if self.tiers:
            return sorted(self.tiers, key=lambda t: t.quality, reverse=True)
        return [Tier(fetch=self.fetch, quality=100, degraded=False, label="default")]
```

### 2. `lib/tiers.py`(新文件)— 降级执行器
```python
def run_tiers(source, query, window, *, env, depth) -> tuple[list[Item], Tier|None]:
    """按 quality 降序试各 tier,第一个返回非空结果的即采用。
    返回 (items, 命中的 tier)。全失败/全空 -> ([], None)。
    每个 tier 独立 try/except:一个 tier 抛错不影响下一个(firecrawl WrappedEngineError 思想)。
    命中 tier 后,给每个 item 打 metadata.tier=label、metadata.degraded=tier.degraded。"""
```

### 3. `lib/sources/reddit.py` — 改造成 tiers + 降级过滤
- `_from_json`(quality=100, degraded=False)+ `_from_rss`(quality=40, degraded=True)。
- **关键修复**:RSS tier 内置标题相关性门槛——query 的实义词必须在标题里真实出现(过滤 "Flea market find" 这类偶然含词)。复用与 douyin 同款的 CJK/ASCII 相关性判断(抽到 `sources/base.py` 的 `title_relevance(query,title)`,douyin 和 reddit-rss 共用)。
- 注册:`Source("reddit","en", tiers=(Tier(_from_json,100,False,"json"), Tier(_from_rss,40,True,"rss")), aliases=...)`。

### 4. `lib/sources/base.py` — 抽公共相关性函数
把 douyin.py 里的 `_relevance(query,word)` 上提为 `title_relevance(query, text) -> float`(ASCII token 重叠 + CJK 子串包含),douyin 和 reddit RSS tier 共用,消除重复。

### 5. `lib/sources/bilibili.py` — 同构改造(可选但一致)
B站现有 primary(wbi search)/fallback(iesdouyin)其实也是 tier。第一版可只接口对齐(把现有两段包成 tiers),不改逻辑,保持已验证行为。**为降低 review 风险,第一版 B站维持原状,仅 Reddit 走新框架**;tiers 框架就位后 B站留作 fast-follow。

### 6. `lastdays.py` `_fetch` — 走 run_tiers
```python
def _fetch(name):
    src = registry.get(name)
    items, tier = tiers.run_tiers(src, topic, window, env=config, depth=depth)
    return name, items
```
其余流程(window filter→score→rank→dedupe)不变,因为 degraded 标记已在 item.metadata 上。

### 7. `lib/score.py` — 降级项已有 -10 无 engagement 惩罚,无需改
(degraded 项 engagement={} → engagement_raw 返回 None → 已扣 10 分。tier 框架不改打分,只确保标记传到。)

### 8. `lib/render.py` — evidence 标注降级 tier
item 头部已显示 engagement;新增:`metadata.degraded` 为真时追加 ` | ⚠ degraded:{tier} (no engagement; relevance-filtered)`。让 agent 综合时知道这是降级证据。

### 9. `lib/schema.py` — to_dict 暴露 tier/degraded
`metadata` 已整体输出,只要 run_tiers 把 tier/degraded 写进 metadata 即可,schema 无需改。

## 测试(EXECUTION 同步写)

- `test_tiers.py`(新):① 多 tier 按 quality 降序;② 高质 tier 非空则不试低质 tier;③ 高质 tier 抛错→降级到低质 tier;④ 全空→([],None);⑤ 命中 tier 的 degraded/label 正确写入 item.metadata。
- `test_reddit_hn.py`(扩展):⑥ json 成功不碰 RSS(已有,适配新接口);⑦ json 403→RSS,且 RSS 项带 degraded=True;⑧ **RSS 相关性过滤**:query="Nvidia" 时 "Flea market find" 被滤掉、"Nvidia hits high" 保留。
- `test_base.py`(新):`title_relevance` 的 ASCII/CJK 用例(从 douyin 测试迁移共用)。
- 全量 pytest 必须全绿(当前 41,新增后预计 ~50)。

## 验收基线(REVIEW gate 三 agent 共同检查)

1. 向后兼容:未改造的源(hackernews/github/polymarket/bilibili/douyin)行为不变,测试全绿。
2. Reddit:`.json` 403 时仍能出结果(RSS),且噪音项(标题不含 query 实义词)被过滤。
3. 诚实:降级 item 在 JSON(metadata.degraded)和 compact(⚠ degraded)中可识别,排序不伪造互动数。
4. 零依赖:无新增第三方 import。
5. 文档:source-policy.md 更新 tier 机制说明。

## 风险

- **B站不在第一版改造**——降低一次性改动面,已验证的 wbi 行为不动。
- RSS 相关性阈值需实测调参(太高漏真帖、太低留噪音);EXECUTION 阶段用真实数据校准。
