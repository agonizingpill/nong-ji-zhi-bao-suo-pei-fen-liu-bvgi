"""覆盖判定：按实际用于训练的样本，判断索赔是否落在模型经验范围内。

train_rows 为当次训练真正使用的样本行（分层划分的训练侧），
行结构 [机型, 部位, 报损工时, 机龄, 渗漏]，与 risk_model.row 一致。
"""

def judge(train_rows, target):
    combos = {}
    for r in train_rows:
        combos.setdefault((r[0], r[1]), []).append(int(r[2]))
    key = (target[0], target[1])
    if key not in combos:
        return 'manual_review', f'训练样本未覆盖机型×部件组合 {key[0]} × {key[1]}'
    lo, hi = min(combos[key]), max(combos[key])
    hours = int(target[2])
    if hours < lo or hours > hi:
        return 'manual_review', f'报损工时 {hours}h 超出该组合训练范围 {lo}–{hi}h'
    return 'covered', ''
