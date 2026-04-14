import yaml
import subprocess
import time
import math
import numpy as np
import csv
import os
import random

# --- CONFIGURATION ---
SCHEDULER_NAME = "default-scheduler"
KUBECONFIG = "--kubeconfig kubeconfig.yaml"

# 👇 CHANGE THIS NAME FOR DIFFERENT TESTS (e.g., "diurnal_default.csv", "diurnal_static.csv")
RESULTS_CSV_FILE = "diurnal/diurnal_default.csv" 

# Simulated 24-Hour Cycle (Starts at 50, peaks at 400, drops back to 50)
day_night_traffic = [50, 100, 200, 300, 400, 300, 150, 50] 

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
            "labels": {"app": "diurnal-test"} # <-- CRITICAL: Allows script to find and delete them at night
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
    pod_counts = [] 

    for ns in node_stats.values():
        
        # Calculate Utilization for LBF
        c_u = min(1.0, ns['used_cpu'] / ns['cap_cpu']) if ns['cap_cpu'] > 0 else 0
        m_u = min(1.0, ns['used_mem'] / ns['cap_mem']) if ns['cap_mem'] > 0 else 0
        cpu_utils.append(c_u)
        mem_utils.append(m_u)
        pod_counts.append(ns['pod_count']) 
        
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
    lbf_p = np.std(pod_counts) / np.mean(pod_counts) if np.mean(pod_counts) > 0 else 0.0 

    return {
        "Total Pods": total_pods,
        "Unscheduled": unscheduled_count,
        "Active Nodes": active_nodes,
        "Total Power (W)": total_power,
        "Avg Resource Fragmentation": paper_frag_score, 
        "LBF CPU": lbf_c,           
        "LBF Mem": lbf_m,           
        "LBF Pod": lbf_p            
    }

# --- MAIN EXECUTION PIPELINE ---
if __name__ == "__main__":
    print(f"--- 🌍 STARTING 24-HOUR DIURNAL SIMULATION ---")
    print(f"📁 Results will be saved to: {RESULTS_CSV_FILE}")
    
    random.seed(42)
    current_pods = 0
    pod_index = 1
    
    file_exists = os.path.isfile(RESULTS_CSV_FILE)
    
    with open(RESULTS_CSV_FILE, mode='a', newline='') as csvfile:
        writer = None
        
        for hour, target_pods in enumerate(day_night_traffic):
            print(f"\n[Hour {hour}] Target Cluster Size: {target_pods} Pods")
            
            if target_pods > current_pods:
                # DAYTIME: Scale UP
                pods_to_add = target_pods - current_pods
                print(f"☀️ Scaling UP: Adding {pods_to_add} pods...")
                
                new_pods = []
                for _ in range(pods_to_add):
                    new_pods.append(create_pod(f"diurnal-pod-{pod_index}"))
                    pod_index += 1
                    
                with open("diurnal_temp.yaml", "w") as f:
                    yaml.dump_all(new_pods, f, default_flow_style=False)
                run_cmd(f"kubectl {KUBECONFIG} apply -f diurnal_temp.yaml")

            elif target_pods < current_pods:
                # NIGHTTIME: Scale DOWN
                pods_to_remove = current_pods - target_pods
                print(f"🌙 Scaling DOWN: Deleting {pods_to_remove} pods to save power...")
                
                # Identify pods to delete
                pod_list_output = run_cmd(f"kubectl {KUBECONFIG} get pods -l app=diurnal-test -o custom-columns=:metadata.name --no-headers")
                active_pod_names = [p.strip() for p in pod_list_output.split('\n') if p.strip()]
                
                pods_to_delete = active_pod_names[:pods_to_remove]
                for p_name in pods_to_delete:
                    run_cmd(f"kubectl {KUBECONFIG} delete pod {p_name} --grace-period=0 --force")
                    
            current_pods = target_pods
            
            # Wait for the AI to recalculate and nodes to scale/shut down
            print("Waiting 55 seconds for AI Smart Master to adjust weights and pods to stabilize...")
            time.sleep(55)
            
            # Fetch live metrics and save to CSV
            print("Fetching live metrics for this hour...")
            metrics = get_live_metrics()
            
            print("📊 Current Cluster State:")
            for key, value in metrics.items():
                if isinstance(value, float):
                    print(f"   {key:<26}: {value:.5f}")
                else:
                    print(f"   {key:<26}: {value}")
                    
            metrics_for_csv = {"Hour": hour, "Target Pods": target_pods, **metrics} 
            
            if writer is None:
                writer = csv.DictWriter(csvfile, fieldnames=metrics_for_csv.keys())
                if not file_exists:
                    writer.writeheader() 
            
            writer.writerow(metrics_for_csv)
            csvfile.flush()