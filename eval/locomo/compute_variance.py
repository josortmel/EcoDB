import json, statistics

def load_metrics(path):
    r5_list, r10_list = [], []
    t1 = t2 = t3 = hit1 = 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            m = r["metrics"]
            r5_list.append(m["recall_any@5"])
            r10_list.append(m["recall_any@10"])
            if m["recall_any@10"] == 0: t1 += 1
            elif m["recall_any@5"] == 0: t2 += 1
            elif m["recall_any@1"] == 0: t3 += 1
            else: hit1 += 1
    return {
        "r5": sum(r5_list) / len(r5_list),
        "r10": sum(r10_list) / len(r10_list),
        "Type1": t1, "Type2": t2, "Type3": t3, "HIT@1": hit1,
        "total": len(r5_list),
    }

runs = []
for i in range(1, 4):
    path = f"eval/locomo/results/baseline_run{i}.jsonl"
    m = load_metrics(path)
    runs.append(m)
    print(f"Run {i}: R@5={m['r5']:.4f}  R@10={m['r10']:.4f}  Type1={m['Type1']}  Type2={m['Type2']}  Type3={m['Type3']}  HIT@1={m['HIT@1']}  total={m['total']}")

r5s = [r["r5"] for r in runs]
r10s = [r["r10"] for r in runs]
print(f"\nR@5:  {statistics.mean(r5s):.4f} ± {statistics.stdev(r5s):.4f}")
print(f"R@10: {statistics.mean(r10s):.4f} ± {statistics.stdev(r10s):.4f}")
print(f"2σ threshold (R@5): {2 * statistics.stdev(r5s):.4f}")
