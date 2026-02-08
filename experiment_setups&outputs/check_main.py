import yaml
import numpy as np
import matplotlib.pyplot as plt
import math
import csv
import os

# --- POWER MODEL PARAMETERS (Paper Version) ---
K0 = 150.0
K1 = 100.0
K2 = 3.0

OUTPUT_DIR = "results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

    cpu_usages = [ns['used_cpu'] for ns in node_stats.values()]
    mem_usages = [ns['used_mem'] for ns in node_stats.values()]
    pod_counts = [ns['pod_count'] for ns in node_stats.values()]

    def lbf(data_list):
        return np.std(data_list) / np.mean(data_list) if np.mean(data_list) > 0 else 0

    lbf_cpu = lbf(cpu_usages)
    lbf_mem = lbf(mem_usages)
    lbf_pod = lbf(pod_counts)

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

        u = np.array([ns['cap_cpu'] - ns['used_cpu'], ns['cap_mem'] - ns['used_mem']])
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

def save_csv(res_default, res_aware):
    csv_path = os.path.join(OUTPUT_DIR, "comparison_results.csv")
    with open(csv_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Metric", "Default Scheduler", "Power-Aware (TOPSIS)", "Improvement (%)"])

        for metric in res_default.keys():
            default_val = res_default[metric]
            aware_val = res_aware[metric]

            if default_val != 0:
                improvement = ((default_val - aware_val) / default_val) * 100
            else:
                improvement = 0

            writer.writerow([metric, default_val, aware_val, improvement])

    print(f"\nCSV saved to {csv_path}")

def plot_comparison(res_default, res_aware):
    for metric in res_default.keys():
        plt.figure(figsize=(6, 4))
        values = [res_default[metric], res_aware[metric]]
        labels = ['Default Scheduler', 'Power-Aware (TOPSIS)']

        bars = plt.bar(labels, values)

        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width()/2,
                height,
                f'{height:.3f}',
                ha='center',
                va='bottom'
            )

        plt.title(metric)
        plt.ylabel("Value")
        plt.tight_layout()

        file_name = metric.replace(" ", "_") + ".png"
        save_path = os.path.join(OUTPUT_DIR, file_name)
        plt.savefig(save_path)
        print(f"Graph saved to {save_path}")

        plt.show()

# --- EXECUTION ---
file1 = 'normaloutput.yml'
file2 = 'poweroutput2.yml'

results_default = get_metrics(file1)
results_aware = get_metrics(file2)

print("\n--- RESULTS ---")
for k in results_default.keys():
    print(f"{k:<15} | Default: {results_default[k]:.4f} | Aware: {results_aware[k]:.4f}")

save_csv(results_default, results_aware)
plot_comparison(results_default, results_aware)
