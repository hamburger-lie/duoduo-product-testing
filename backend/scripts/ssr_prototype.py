# -*- coding: utf-8 -*-
"""SSR（语义相似度评分）计算链路原型 + 数值验证。

演算内容：
  1. 温度对 softmax 的影响 —— 为什么裸 softmax 会失真
  2. 余弦相似度 -> Likert 分布 -> 期望值
  3. 群体分布聚合：SSR 分布加总 vs 整数投票，尾部保留对比
  4. 概率 NPS vs 整数 NPS
  5. 同角色 k 次采样（context_card）的人内方差
"""
import numpy as np

np.set_printoptions(precision=3, suppress=True)
rng = np.random.default_rng(42)

LEVELS = np.array([1, 2, 3, 4, 5])


def softmax(x, tau):
    z = (np.asarray(x, dtype=float)) / tau
    z -= z.max()  # 数值稳定
    e = np.exp(z)
    return e / e.sum()


def expected(p):
    return float(np.dot(p, LEVELS))


# ================================================================
# 1) 温度实验：真实 embedding 的余弦相似度都挤在一个窄区间
#    （比如 0.60~0.80），裸 softmax(tau=1) 会输出近似均匀分布
# ================================================================
print("=" * 64)
print("【1】温度 tau 的影响（模拟一条偏正面的回答）")
# 模拟：回答「挺想买的，就是等个活动」与 5 档锚定句的余弦相似度
sims = np.array([0.58, 0.63, 0.72, 0.80, 0.74])  # 1..5 档
print(f"余弦相似度: {sims}   (最像 4 分档)")
for tau in [1.0, 0.3, 0.1, 0.05, 0.02]:
    p = softmax(sims, tau)
    ent = -np.sum(p * np.log(p + 1e-12)) / np.log(5)  # 归一化熵 0~1
    print(f"  tau={tau:<5} -> P={p}  E={expected(p):.2f}  归一化熵={ent:.2f}")

# ================================================================
# 2) 三条典型回答的完整映射
# ================================================================
print()
print("=" * 64)
print("【2】三条典型回答 -> 分布 -> 期望值 (tau=0.05)")
TAU = 0.05
cases = {
    "强正面「已经加购了，这价格闭眼冲」": np.array([0.52, 0.55, 0.63, 0.74, 0.83]),
    "观望「感觉还行，先收藏看看测评」":   np.array([0.55, 0.62, 0.79, 0.72, 0.60]),
    "偏负面「香精排那么前，我敏皮不敢碰」": np.array([0.78, 0.80, 0.66, 0.57, 0.52]),
}
case_dists = {}
for text, s in cases.items():
    p = softmax(s, TAU)
    case_dists[text] = p
    print(f"  {text}")
    print(f"    P={p}  E={expected(p):.2f}  众数={LEVELS[p.argmax()]}")

# ================================================================
# 3) 群体聚合：30 个角色
#    对比 (a) 每人一票整数(众数/argmax) 与 (b) SSR 分布直接加总
# ================================================================
print()
print("=" * 64)
print("【3】30 个角色的群体分布：整数投票 vs SSR 分布加总")
# 构造 30 个角色的"真实态度"（连续值，均值3.4，有极端个体）
true_attitude = np.clip(rng.normal(3.4, 1.1, 30), 1, 5)
pop_dists = []
for a in true_attitude:
    # 相似度 = 以 true_attitude 为中心的钟形 + 少量噪声
    s = 0.6 + 0.2 * np.exp(-0.5 * ((LEVELS - a) / 1.0) ** 2) + rng.normal(0, 0.01, 5)
    pop_dists.append(softmax(s, TAU))
pop_dists = np.array(pop_dists)

ssr_agg = pop_dists.mean(axis=0)                    # (b) 分布加总（归一化）
votes = pop_dists.argmax(axis=1) + 1                # (a) 每人取众数当整数票
vote_agg = np.array([(votes == k).mean() for k in LEVELS])

print(f"  真实态度均值: {true_attitude.mean():.2f}")
print(f"  整数投票分布 : {vote_agg}   (尾部: 1分{vote_agg[0]:.1%} 5分{vote_agg[4]:.1%})")
print(f"  SSR聚合分布  : {ssr_agg}   (尾部: 1分{ssr_agg[0]:.1%} 5分{ssr_agg[4]:.1%})")
print(f"  整数版均值={float((vote_agg*LEVELS).sum()):.3f}  SSR版均值={float((ssr_agg*LEVELS).sum()):.3f}  真实={true_attitude.mean():.3f}")

# 换算成前端可用的"人数"（乘 N 后最大余数法取整，保证加和=N）
N = 30
raw = ssr_agg * N
floor = np.floor(raw).astype(int)
remainder = raw - floor
short = N - floor.sum()
idx = np.argsort(-remainder)[:short]
counts = floor.copy()
counts[idx] += 1
print(f"  SSR -> 前端人数(加和={counts.sum()}): {dict(zip(LEVELS.tolist(), counts.tolist()))}")

# ================================================================
# 4) NPS：整数版 vs 概率版
# ================================================================
print()
print("=" * 64)
print("【4】NPS 两种算法")
# 整数版（现行逻辑近似）：5分=推荐者, 1-2分=贬损者
nps_int = ((votes == 5).mean() - (votes <= 2).mean()) * 100
# 概率版：每人 P(5) 与 P(1)+P(2)
p_prom = pop_dists[:, 4].mean()
p_detr = pop_dists[:, :2].sum(axis=1).mean()
nps_prob = (p_prom - p_detr) * 100
print(f"  整数版 NPS = {nps_int:+.1f}")
print(f"  概率版 NPS = {nps_prob:+.1f}   (推荐概率均值={p_prom:.3f}, 贬损概率均值={p_detr:.3f})")
print("  注意：两者口径不同，切换时报告里要标注，不可直接和历史值比较")

# ================================================================
# 5) 同角色 k 次采样（不同 context_card）
# ================================================================
print()
print("=" * 64)
print("【5】同一角色 k=5 次采样（不同情境卡）的人内方差")
base = 3.6  # 该角色的基线态度
contexts = {"刚发工资": +0.5, "月底吃土": -0.7, "闺蜜安利过": +0.4, "被同类坑过": -0.5, "普通日常": 0.0}
per_sample = []
for name, shift in contexts.items():
    a = np.clip(base + shift, 1, 5)
    s = 0.6 + 0.2 * np.exp(-0.5 * ((LEVELS - a) / 1.0) ** 2)
    p = softmax(s, TAU)
    per_sample.append(p)
    print(f"  {name:<8} E={expected(p):.2f}  P={p}")
per_sample = np.array(per_sample)
persona_dist = per_sample.mean(axis=0)
es = per_sample @ LEVELS
print(f"  角色最终分布 = 各次平均: {persona_dist}")
print(f"  期望均值={es.mean():.2f}  期望标准差(人内方差)={es.std(ddof=1):.2f}")
print("  -> 这个标准差就是报告 confidence 的真实依据")
