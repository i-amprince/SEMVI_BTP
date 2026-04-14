import yaml
import random
import subprocess
import time
import math
import numpy as np
import csv
import os

# --- CONFIGURATION ---
BATCH_SIZE = 50
TOTAL_BATCHES = 1
SCHEDULER_NAME = "power-aware-scheduler"

KUBECONFIG = "--kubeconfig kubeconfig.yaml"

# 👇 CHANGE THIS NAME FOR DIFFERENT TESTS (e.g., "results_xgboost.csv", "results_static.csv")
RESULTS_CSV_FILE = "output_comparisons/testing.csv" 

# Power Model
K0 = 10.0 
K1 = 5.0
K2 = 4.0

# Pod Sizing
CPU_MIN_CORES = 0.5
CPU_MAX_CORES = 1.5
MEM_MIN_MIB   = 4096  # 4 GiB
MEM_MAX_MIB   = 6144  # 6 GiB

# --- HELPER FUNCTIONS ---
def run_cmd(cmd):
    """Executes a shell command and returns the output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command Error: {result.stderr}")
    return result.stdout

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

def create_pod(name: str) -> dict:
    cpu_cores = round(random.uniform(CPU_MIN_CORES, CPU_MAX_CORES), 2)
    cpu_milli = int(cpu_cores * 1000)
    mem = random.randint(MEM_MIN_MIB, MEM_MAX_MIB)
    
    return {
        "apiVersion": "v1",
        "kind":       "Pod",
        "metadata":   {
            "name": name,
            "namespace": "default",
        },
        "spec": {
            "schedulerName": SCHEDULER_NAME,
            "restartPolicy": "Never",
            "containers": [{
                "name":  "workload",
                "image": "nginx:stable-alpine",
                "resources": {
                    "requests": {"cpu": f"{cpu_milli}m", "memory": f"{mem}Mi"},
                    "limits":   {"cpu": f"{cpu_milli}m", "memory": f"{mem}Mi"},
                },
            }],
        },
    }

def get_live_metrics():
    """Fetches live cluster state and calculates power & distribution metrics."""
    nodes_raw = yaml.safe_load(run_cmd(f"kubectl {KUBECONFIG} get nodes -o yaml"))
    pods_raw = yaml.safe_load(run_cmd(f"kubectl {KUBECONFIG} get pods -o yaml"))
    
    if not nodes_raw or 'items' not in nodes_raw: 
        return {"Error": "Could not fetch nodes"}

    node_stats = {}
    for n in nodes_raw.get('items', []):
        name = n['metadata']['name']
        alloc = n.get('status', {}).get('allocatable', n.get('status', {}).get('capacity', {}))
        node_stats[name] = {
            'cap_cpu': parse_cpu(alloc.get('cpu', '1')),
            'cap_mem': parse_mem(alloc.get('memory', '1G')),
            'used_cpu': 0.0,
            'used_mem': 0.0,
            'pod_count': 0
        }

    total_pods = len(pods_raw.get('items', []))
    unscheduled_count = 0

    for p in pods_raw.get('items', []):
        node_name = p.get('spec', {}).get('nodeName')
        if not node_name or node_name not in node_stats:
            unscheduled_count += 1
            continue

        node_stats[node_name]['pod_count'] += 1
        for container in p.get('spec', {}).get('containers', []):
            req = container.get('resources', {}).get('requests', {})
            node_stats[node_name]['used_cpu'] += parse_cpu(req.get('cpu', 0))
            node_stats[node_name]['used_mem'] += parse_mem(req.get('memory', 0))

    # Calculate Power & Fragmentation
    total_power = 0
    active_nodes = 0
    node_frags = []
    
    # Lists to calculate LBF
    cpu_utils = [] 
    mem_utils = []
    pod_counts = [] # <-- NEW: Added to track pod distribution

    for ns in node_stats.values():
        
        # Calculate Utilization for LBF
        c_u = min(1.0, ns['used_cpu'] / ns['cap_cpu']) if ns['cap_cpu'] > 0 else 0
        m_u = min(1.0, ns['used_mem'] / ns['cap_mem']) if ns['cap_mem'] > 0 else 0
        cpu_utils.append(c_u)
        mem_utils.append(m_u)
        pod_counts.append(ns['pod_count']) # <-- NEW: Track pods per node
        
        # --- Fragmentation Math (L2 Norm) ---
        u_vec = np.array([max(ns['cap_cpu'] - ns['used_cpu'], 0), max(ns['cap_mem'] - ns['used_mem'], 0)])
        v_vec = np.array([ns['cap_cpu'], ns['cap_mem']])
        frag = np.linalg.norm(u_vec) / np.linalg.norm(v_vec) if np.linalg.norm(v_vec) > 0 else 0
        node_frags.append(frag)

        if ns['pod_count'] > 0:
            active_nodes += 1
            util = c_u 
            
            # --- Power Math ---
            cores = ns['cap_cpu']
            node_k0 = K0 * cores
            node_k1 = K1 * cores
            power = node_k0 + node_k1 * (1.0 - math.exp(-K2 * util))
            total_power += power

    # Calculate Final Scores
    avg_node_frag = np.mean(node_frags) if node_frags else 0.0
    u_ratio = unscheduled_count / total_pods if total_pods > 0 else 0.0
    
    # Paper exact formula: Average Frag * Unschedulable Ratio
    paper_frag_score = avg_node_frag * u_ratio
    
    # Calculate LBFs exactly as formulated in the paper
    lbf_c = np.std(cpu_utils) / np.mean(cpu_utils) if np.mean(cpu_utils) > 0 else 0.0
    lbf_m = np.std(mem_utils) / np.mean(mem_utils) if np.mean(mem_utils) > 0 else 0.0
    lbf_p = np.std(pod_counts) / np.mean(pod_counts) if np.mean(pod_counts) > 0 else 0.0 # <-- NEW: LBF Pods

    return {
        "Total Pods": total_pods,
        "Unscheduled": unscheduled_count,
        "Active Nodes": active_nodes,
        "Total Power (W)": total_power,
        "Avg Resource Fragmentation": paper_frag_score, # <-- RENAMED to match paper terminology perfectly
        "LBF CPU": lbf_c,           
        "LBF Mem": lbf_m,           
        "LBF Pod": lbf_p            # <-- NEW: Added to final metrics
    }

# --- MAIN EXECUTION PIPELINE ---
if __name__ == "__main__":
    print(f"🚀 Starting Staged Deployment using: {SCHEDULER_NAME}")
    print(f"📁 Results will be saved to: {RESULTS_CSV_FILE}")
    
    pod_index = 0
    random.seed(42)
    
    file_exists = os.path.isfile(RESULTS_CSV_FILE)
    
    with open(RESULTS_CSV_FILE, mode='a', newline='') as csvfile:
        writer = None
        
        for batch in range(1, TOTAL_BATCHES + 1):
            print(f"\n--- BATCH {batch}/{TOTAL_BATCHES} ---")
            print(f"Generating {BATCH_SIZE} new pods...")
            
            # 1. Generate Pods
            pods = []
            for _ in range(BATCH_SIZE):
                pods.append(create_pod(f"demo-pod-{pod_index}"))
                pod_index += 1
                
            with open("staged_pods.yaml", "w") as f:
                yaml.dump_all(pods, f, default_flow_style=False)
                
            # 2. Apply Pods
            print("Submitting to cluster...")
            run_cmd(f"kubectl {KUBECONFIG} apply -f staged_pods.yaml")
            
            # 3. Wait for Scheduler
            print("Waiting 35 seconds for scheduler & AI to place workloads...")
            time.sleep(55) 
            
            # 4. Fetch and Calculate Live Metrics
            print("Fetching live metrics...")
            metrics = get_live_metrics()
            
            # 5. Display Results
            print("📊 Current Cluster State:")
            for key, value in metrics.items():
                if isinstance(value, float):
                    print(f"   {key:<26}: {value:.5f}")
                else:
                    print(f"   {key:<26}: {value}")
                    
            # 6. Save to CSV
            metrics_for_csv = {"Batch": batch, **metrics} 
            
            if writer is None:
                writer = csv.DictWriter(csvfile, fieldnames=metrics_for_csv.keys())
                if not file_exists:
                    writer.writeheader() 
            
            writer.writerow(metrics_for_csv)
            csvfile.flush()