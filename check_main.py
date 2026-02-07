import yaml
import numpy as np
import matplotlib.pyplot as plt
import math

# --- POWER MODEL PARAMETERS ---
K0 = 150.0
K1 = 100.0
K2 = 3.0

def parse_cpu(cpu_val):
    if not cpu_val: return 0.0
    cpu_str = str(cpu_val)
    if cpu_str.endswith('m'): return float(cpu_str[:-1]) / 1000.0
    return float(cpu_str)

def parse_mem(mem_val):
    if not mem_val: return 0.0
    mem_str = str(mem_val).replace('i', '')
    if mem_str.endswith('G'): return float(mem_str[:-1])
    if mem_str.endswith('M'): return float(mem_str[:-1]) / 1024.0
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

    # --- LBF ---
    cpu_usages = [ns['used_cpu'] for ns in node_stats.values()]
    mem_usages = [ns['used_mem'] for ns in node_stats.values()]
    pod_counts = [ns['pod_count'] for ns in node_stats.values()]

    def lbf(data_list):
        return np.std(data_list) / np.mean(data_list) if np.mean(data_list) > 0 else 0

    lbf_cpu = lbf(cpu_usages)
    lbf_mem = lbf(mem_usages)
    lbf_pod = lbf(pod_counts)

    # --- POWER & RF ---
    total_power = 0
    active_nodes = 0
    rf_values = []
    unscheduled_ratio = unscheduled_count / len(pods) if pods else 0

    for ns in node_stats.values():

        # 🔥 ONLY COUNT ACTIVE NODES
        if ns['pod_count'] > 0:
            active_nodes += 1
            util = min(1.0, ns['used_cpu'] / ns['cap_cpu']) if ns['cap_cpu'] > 0 else 0
            power = K0 + K1 * (1 - math.exp(-K2 * util))
            total_power += power

        # Resource Fragmentation
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

def plot_comparison(res_default, res_aware):
    labels = list(res_default.keys())
    def_vals = [res_default[l] for l in labels]
    awa_vals = [res_aware[l] for l in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width/2, def_vals, width, label='Default Scheduler')
    ax.bar(x + width/2, awa_vals, width, label='Power-Aware (TOPSIS)')

    ax.set_ylabel('Metric Value')
    ax.set_title('Comparison: Default vs Power-Aware Scheduler')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45)
    ax.legend()
    plt.tight_layout()
    plt.show()

# --- EXECUTION ---
file1 = 'normaloutput.yml'
file2 = 'poweroutput.yml'

print("Extracting metrics...")
results_default = get_metrics(file1)
results_aware = get_metrics(file2)

print("\n--- RESULTS ---")
for k in results_default.keys():
    print(f"{k:<15} | Default: {results_default[k]:.4f} | Aware: {results_aware[k]:.4f}")

plot_comparison(results_default, results_aware)
