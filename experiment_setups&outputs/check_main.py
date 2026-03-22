import argparse
import csv
import math
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

# Defaults now represent Watts per Core
DEFAULT_K0 = 10.0
DEFAULT_K1 = 5.0
DEFAULT_K2 = 4.0
OUTPUT_DIR = "results"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def parse_cpu(val) -> float:
    if not val:
        return 0.0
    s = str(val).strip()
    if s.endswith('m'):
        return float(s[:-1]) / 1000.0
    return float(s)

def parse_mem(val) -> float:
    if not val:
        return 0.0
    s = str(val).strip().replace('i', '')
    if s.endswith('G'): return float(s[:-1])
    if s.endswith('M'): return float(s[:-1]) / 1024.0
    if s.endswith('K'): return float(s[:-1]) / (1024.0 ** 2)
    return float(s) / (1024.0 ** 3)

def coeff_of_variation(values: list) -> float:
    arr = np.array(values, dtype=float)
    mu = arr.mean()
    return float(arr.std() / mu) if mu > 1e-9 else 0.0

def get_metrics(file_path: str, k0: float, k1: float, k2: float) -> dict:
    if not os.path.exists(file_path):
        sys.exit(f"ERROR: File not found: {file_path}")
        
    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)

    raw_nodes = data.get('nodes', [])
    raw_pods  = data.get('pods',  [])

    node_stats = {}
    for n in raw_nodes:
        name   = n['metadata']['name']
        status = n.get('status', {})
        alloc = status.get('allocatable', status.get('capacity', {}))

        node_stats[name] = {
            'cap_cpu': parse_cpu(alloc.get('cpu', '1')),
            'cap_mem': parse_mem(alloc.get('memory', '1G')),
            'used_cpu': 0.0,
            'used_mem': 0.0,
            'pod_count': 0,
        }

    total_pods = len(raw_pods)
    unscheduled_count = 0

    for p in raw_pods:
        spec      = p.get('spec', {})
        node_name = spec.get('nodeName')

        if not node_name or node_name not in node_stats:
            unscheduled_count += 1
            continue

        node_stats[node_name]['pod_count'] += 1

        for container in spec.get('containers', []):
            req = container.get('resources', {}).get('requests', {})
            node_stats[node_name]['used_cpu'] += parse_cpu(req.get('cpu', 0))
            node_stats[node_name]['used_mem'] += parse_mem(req.get('memory', 0))

    cpu_utils  = []
    mem_utils  = []
    pod_counts = []
    total_power = 0.0
    rf_values = []

    unscheduled_ratio = unscheduled_count / total_pods if total_pods > 0 else 0.0

    for ns in node_stats.values():
        cpu_u = (ns['used_cpu'] / ns['cap_cpu']) if ns['cap_cpu'] > 0 else 0.0
        mem_u = (ns['used_mem'] / ns['cap_mem']) if ns['cap_mem'] > 0 else 0.0
        
        util = min(cpu_u, 1.0)
        cpu_utils.append(util)
        mem_utils.append(min(mem_u, 1.0))
        pod_counts.append(ns['pod_count'])

        # Heterogeneous Power Calculation
        if ns['pod_count'] > 0:
            cores = ns['cap_cpu'] if ns['cap_cpu'] > 0 else 1.0
            node_k0 = k0 * cores
            node_k1 = k1 * cores
            power = node_k0 + node_k1 * (1.0 - math.exp(-k2 * util))
            total_power += power

        u = np.array([
            max(ns['cap_cpu'] - ns['used_cpu'], 0.0),
            max(ns['cap_mem'] - ns['used_mem'], 0.0),
        ])
        v = np.array([ns['cap_cpu'], ns['cap_mem']])

        norm_v = np.linalg.norm(v)
        rfi = (np.linalg.norm(u) / norm_v) * unscheduled_ratio if norm_v > 1e-9 else 0.0
        rf_values.append(rfi)

    avg_rf = float(np.mean(rf_values)) if rf_values else 0.0

    return {
        "LBF (CPU)":                      coeff_of_variation(cpu_utils),
        "LBF (Memory)":                   coeff_of_variation(mem_utils),
        "LBF (Pod)":                      coeff_of_variation(pod_counts),
        "Average Power Consumption (W)":  total_power, 
        "Average Resource Fragmentation": avg_rf,
        "Unscheduled Pods Ratio":         unscheduled_ratio,
    }

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--k0", type=float, default=DEFAULT_K0)
    p.add_argument("--k1", type=float, default=DEFAULT_K1)
    p.add_argument("--k2", type=float, default=DEFAULT_K2)
    p.add_argument("--exp1-power",   default=None)
    p.add_argument("--exp1-default", default=None)
    p.add_argument("--exp2-power",   default=None)
    p.add_argument("--exp2-default", default=None)
    p.add_argument("--exp3-power",   default=None)
    p.add_argument("--exp3-default", default=None)
    return p.parse_args()

def main():
    args = parse_args()
    k0, k1, k2 = args.k0, args.k1, args.k2

    experiments = []
    for i in (1, 2, 3):
        pf = getattr(args, f"exp{i}_power")
        df = getattr(args, f"exp{i}_default")
        if pf and df:
            experiments.append((f"Experiment {i}", df, pf))

    if not experiments:
        sys.exit("No experiment files supplied.")

    results = {}

    for label, df, pf in experiments:
        r_default = get_metrics(df, k0, k1, k2)
        r_power   = get_metrics(pf, k0, k1, k2)
        results[label] = {"default": r_default, "power": r_power}

    csv_path = os.path.join(OUTPUT_DIR, "comparison_results.csv")
    metric_names = list(next(iter(results.values()))["default"].keys())

    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        header = ["Metric"]
        for label in results:
            header += [f"{label} - Default", f"{label} - Power-Aware"]
        w.writerow(header)
        
        for metric in metric_names:
            row = [metric]
            for label in results:
                row.append(results[label]["default"][metric])
                row.append(results[label]["power"][metric])
            w.writerow(row)

    exp_labels  = list(results.keys())
    n_exp       = len(exp_labels)
    n_metrics   = len(metric_names)

    cols = 3
    rows = math.ceil(n_metrics / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(15, 8))
    fig.suptitle('Power-aware scheduler vs Default Kubernetes scheduler', fontsize=14, fontweight='bold')
    
    if n_metrics == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    x     = np.arange(n_exp)
    width = 0.35
    
    for idx, metric in enumerate(metric_names):
        ax = axes[idx]

        default_vals = [results[lbl]["default"][metric] for lbl in exp_labels]
        power_vals   = [results[lbl]["power"][metric]   for lbl in exp_labels]

        ax.bar(x - width / 2, power_vals,   width, label="Power-aware scheduler", color="#539caf")
        ax.bar(x + width / 2, default_vals, width, label="Default scheduler", color="#c9142b")

        ax.set_xticks(x)
        ax.set_xticklabels(exp_labels, fontsize=10)
        ax.set_title(metric, fontsize=11, fontweight='bold')

    for j in range(idx + 1, len(axes)):
        fig.delaxes(axes[j])

    handles, labels_legend = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_legend, loc="lower center", ncol=2, fontsize=12, frameon=False, bbox_to_anchor=(0.5, -0.05))
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    plot_path = os.path.join(OUTPUT_DIR, "Fig2_Reproduction.png")
    plt.savefig(plot_path, dpi=200, bbox_inches='tight')

if __name__ == "__main__":
    main()