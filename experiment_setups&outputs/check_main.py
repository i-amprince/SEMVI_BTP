import yaml
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os

# --- POWER MODEL PARAMETERS ---
K0 = 150.0
K1 = 100.0
K2 = 3.0

OUTPUT_DIR = "results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------
# Parsing helpers
# -------------------------------
def parse_cpu(cpu_val):
    if not cpu_val:
        return 0.0
    cpu_str = str(cpu_val)
    if cpu_str.endswith('m'):
        return float(cpu_str[:-1]) / 1000.0
    return float(cpu_str)

def parse_mem(mem_val):
    if not mem_val:
        return 0.0
    mem_str = str(mem_val).replace('i', '')
    if mem_str.endswith('G'):
        return float(mem_str[:-1])
    if mem_str.endswith('M'):
        return float(mem_str[:-1]) / 1024.0
    return float(mem_str)

# -------------------------------
# Metric computation
# -------------------------------
def get_metrics(file_path):
    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)

    nodes = data.get('nodes', [])
    pods = data.get('pods', [])

    node_stats = {}

    for n in nodes:
        name = n['metadata']['name']
        node_stats[name] = {
            'cap_cpu': parse_cpu(n['status']['capacity']['cpu']),
            'cap_mem': parse_mem(n['status']['capacity']['memory']),
            'used_cpu': 0.0,
            'used_mem': 0.0,
            'pod_count': 0
        }

    unscheduled_count = 0

    for p in pods:
        node_name = p.get('spec', {}).get('nodeName')
        if not node_name:
            unscheduled_count += 1
            continue

        if node_name in node_stats:
            node_stats[node_name]['pod_count'] += 1
            for container in p['spec']['containers']:
                req = container.get('resources', {}).get('requests', {})
                node_stats[node_name]['used_cpu'] += parse_cpu(req.get('cpu', 0))
                node_stats[node_name]['used_mem'] += parse_mem(req.get('memory', 0))

    # ---- UTILIZATION BASED LBF (important correction) ----
    cpu_utils = [
        ns['used_cpu'] / ns['cap_cpu'] if ns['cap_cpu'] > 0 else 0
        for ns in node_stats.values()
    ]

    mem_utils = [
        ns['used_mem'] / ns['cap_mem'] if ns['cap_mem'] > 0 else 0
        for ns in node_stats.values()
    ]

    pod_counts = [ns['pod_count'] for ns in node_stats.values()]

    def lbf(data_list):
        return np.std(data_list) / np.mean(data_list) if np.mean(data_list) > 0 else 0

    lbf_cpu = lbf(cpu_utils)
    lbf_mem = lbf(mem_utils)
    lbf_pod = lbf(pod_counts)

    # ---- Power & RF ----
    total_power = 0
    active_nodes = 0
    rf_values = []

    unscheduled_ratio = unscheduled_count / len(pods) if pods else 0

    for ns in node_stats.values():

        if ns['pod_count'] > 0:
            active_nodes += 1

        util = min(1.0, ns['used_cpu'] / ns['cap_cpu']) if ns['cap_cpu'] > 0 else 0
        power = K0 + K1 * math.exp(-K2 * util)
        total_power += power

        u = np.array([ns['cap_cpu'] - ns['used_cpu'],
                      ns['cap_mem'] - ns['used_mem']])
        v = np.array([ns['cap_cpu'], ns['cap_mem']])

        rfi = (np.linalg.norm(u) / np.linalg.norm(v)) * unscheduled_ratio
        rf_values.append(rfi)

    avg_rf = np.mean(rf_values)

    return {
        "LBF CPU": lbf_cpu,
        "LBF Mem": lbf_mem,
        "LBF Pod": lbf_pod,
        "Active Nodes": active_nodes,
        "Total Power": total_power,
        "Avg RF": avg_rf
    }

# -------------------------------
# Input files
# -------------------------------
normal_small = "normal_small.yml"
power_small  = "power_small.yml"
normal_big   = "normaloutput.yml"
power_big    = "poweroutput2.yml"

# -------------------------------
# Compute metrics
# -------------------------------
res_ns = get_metrics(normal_small)
res_ps = get_metrics(power_small)
res_nb = get_metrics(normal_big)
res_pb = get_metrics(power_big)

# -------------------------------
# Save CSV
# -------------------------------
csv_path = os.path.join(OUTPUT_DIR, "comparison_results.csv")

with open(csv_path, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Metric",
                     "Normal Small", "Power Small",
                     "Normal Big", "Power Big"])

    for metric in res_ns.keys():
        writer.writerow([
            metric,
            res_ns[metric],
            res_ps[metric],
            res_nb[metric],
            res_pb[metric]
        ])

print(f"\nCSV saved to {csv_path}")

# -------------------------------
# Plot (Paper-style format)
# -------------------------------
for metric in res_ns.keys():

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.suptitle(metric)

    # --- Small cluster subplot ---
    small_vals = [res_ns[metric], res_ps[metric]]
    axes[0].bar(['Default', 'Power-Aware'], small_vals)
    axes[0].set_title("Small Cluster")
    axes[0].set_ylabel("Value")

    # --- Big cluster subplot ---
    big_vals = [res_nb[metric], res_pb[metric]]
    axes[1].bar(['Default', 'Power-Aware'], big_vals)
    axes[1].set_title("Big Cluster")

    plt.tight_layout()

    save_path = os.path.join(OUTPUT_DIR,
                             metric.replace(" ", "_") + ".png")
    plt.savefig(save_path)
    print(f"Graph saved to {save_path}")

    plt.show()
