import subprocess
import yaml
import time
import csv
import random
import numpy as np
import math
import threading
from flask import Flask, jsonify
import logging

# --- CORE SETTINGS ---
# Constants for your power model
K0, K1, K2 = 10.0, 5.0, 4.0
CPU_MIN, CPU_MAX = 0.5, 1.5
MEM_MIN, MEM_MAX = 4096, 6144  

# --- API SERVER SETUP ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Shared memory for weights
current_weights = {
    "pods": 0.25,
    "cpu": 0.25,
    "memory": 0.25,
    "power": 0.25
}

@app.route('/get_weights', methods=['GET'])
def get_weights():
    return jsonify(current_weights)

def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- UTILITY FUNCTIONS ---
def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def parse_cpu(val) -> float:
    if not val: return 0.0
    s = str(val).strip()
    if s.endswith('m'): return float(s[:-1]) / 1000.0
    return float(s)

def parse_mem(val) -> float:
    if not val: return 0.0
    s = str(val).strip().replace('i', '')
    if s.endswith('G'): return float(s[:-1])
    if s.endswith('M'): return float(s[:-1]) / 1024.0
    return float(s) / (1024.0 ** 3) # Normalize to GB

def coeff_of_variation(values: list) -> float:
    arr = np.array(values, dtype=float)
    mu = arr.mean()
    return float(arr.std() / mu) if mu > 1e-9 else 0.0

# --- METRICS EXTRACTION ---
def get_live_metrics():
    # Using your specific kubeconfig
    k_cfg = "--kubeconfig kubeconfig.yaml"
    nodes_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get nodes -o yaml"))
    pods_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get pods -o yaml"))
    
    if not nodes_raw or 'items' not in nodes_raw:
        return [0.0] * 8
        
    node_stats = {}
    cluster_cap_cpu = cluster_cap_mem = 0.0
    
    for n in nodes_raw['items']:
        name = n['metadata']['name']
        alloc = n.get('status', {}).get('allocatable', n.get('status', {}).get('capacity', {}))
        c_cap, m_cap = parse_cpu(alloc.get('cpu', '1')), parse_mem(alloc.get('memory', '1G'))
        node_stats[name] = {'cap_c': c_cap, 'cap_m': m_cap, 'u_c': 0.0, 'u_m': 0.0, 'pod_count': 0}
        cluster_cap_cpu += c_cap
        cluster_cap_mem += m_cap

    total_pods = len(pods_raw.get('items', []))
    unscheduled = 0

    for p in pods_raw.get('items', []):
        node_name = p.get('spec', {}).get('nodeName')
        if not node_name or node_name not in node_stats:
            unscheduled += 1
            continue
            
        node_stats[node_name]['pod_count'] += 1
        for container in p.get('spec', {}).get('containers', []):
            req = container.get('resources', {}).get('requests', {})
            node_stats[node_name]['u_c'] += parse_cpu(req.get('cpu', 0))
            node_stats[node_name]['u_m'] += parse_mem(req.get('memory', 0))

    cpu_utils, mem_utils, rf_values = [], [], []
    total_power = cluster_used_c = cluster_used_m = 0.0
    u_ratio = unscheduled / total_pods if total_pods > 0 else 0.0

    for ns in node_stats.values():
        cluster_used_c += ns['u_c']
        cluster_used_m += ns['u_m']
        c_u, m_u = (ns['u_c']/ns['cap_c']), (ns['u_m']/ns['cap_m'])
        cpu_utils.append(min(c_u, 1.0))
        mem_utils.append(min(m_u, 1.0))

        if ns['pod_count'] > 0:
            # Heterogeneous Power Model Calculation
            power = (K0 * ns['cap_c']) + (K1 * ns['cap_c']) * (1.0 - math.exp(-K2 * min(c_u, 1.0)))
            total_power += power

        # Resource Fragmentation
        u = np.array([max(ns['cap_c'] - ns['u_c'], 0.0), max(ns['cap_m'] - ns['u_m'], 0.0)])
        norm_v = np.linalg.norm(np.array([ns['cap_c'], ns['cap_m']]))
        rf_values.append((np.linalg.norm(u) / norm_v) * u_ratio if norm_v > 1e-9 else 0.0)

    return (cluster_used_c / cluster_cap_cpu, 
            cluster_used_m / cluster_cap_mem, 
            float(np.mean(rf_values)), 
            u_ratio, 
            total_power, 
            coeff_of_variation(cpu_utils), 
            coeff_of_variation(mem_utils))

# --- POD DEPLOYMENT ---
def deploy_batch(batch_id, count, ep):
    pods = []
    for i in range(count):
        c_cores = round(random.uniform(CPU_MIN, CPU_MAX), 2)
        mem_mib = random.randint(MEM_MIN, MEM_MAX)
        pods.append({
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": f"p-e{ep}-b{batch_id}-{i}"},
            "spec": {
                "schedulerName": "power-aware-scheduler", "restartPolicy": "Never",
                "containers": [{
                    "name": "workload", "image": "nginx:stable-alpine",
                    "resources": {
                        "requests": {"cpu": f"{int(c_cores*1000)}m", "memory": f"{mem_mib}Mi"},
                        "limits":   {"cpu": f"{int(c_cores*1000)}m", "memory": f"{mem_mib}Mi"}
                    }
                }]
            }
        })
    with open("temp_pods.yaml", "w") as f:
        yaml.dump_all(pods, f)
    run_cmd("kubectl --kubeconfig kubeconfig.yaml apply -f temp_pods.yaml")

# --- MAIN DATA COLLECTION ---
def start_collection(episodes=100):
    global current_weights
    print("="*60)
    print("🚀 BTP: POWER-AWARE SCHEDULER ML DATA COLLECTION")
    print("="*60)
    
    with open("btp_perfect_dataset.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["s_cpu", "s_mem", "s_frag", "w_pod", "w_cpu", "w_mem", "w_pow", 
                         "r_frag", "r_unsched", "r_pow", "r_lbf_c", "r_lbf_m"])

        for ep in range(episodes):
            print(f"\n>>> Starting Episode {ep+1}/{episodes} | Resetting Cluster...")
            
            # 1. Try a standard delete first
            run_cmd("kubectl --kubeconfig kubeconfig.yaml delete pods --all")
            
            # 2. Wait for up to 60 seconds for a clean exit
            wait_output = run_cmd("kubectl --kubeconfig kubeconfig.yaml wait --for=delete pod --all --timeout=60s")
            
            # 3. CHECK: If the pods are still there (wait timed out), use the FORCE HAMMER
            if "timed out" in wait_output.lower() or "error" in wait_output.lower():
                print("⚠️ Warning: Pods stuck! Applying Force Delete...")
                # --force and --grace-period=0 kills them instantly from the API server
                run_cmd("kubectl --kubeconfig kubeconfig.yaml delete pods --all --force --grace-period=0")
                time.sleep(5) # Give the simulator 5 seconds to clear its memory
            
            print("✅ Cluster Clean. Baseline at 0.0.")
            
            for batch in range(13):
                # 1. Capture State BEFORE decision
                s_c, s_m, s_f, _, _, _, _ = get_live_metrics()
                pod_count = batch * 50
                
                # 2. Decision: Randomize Weights
                w = [random.uniform(0.1, 1.0) for _ in range(4)]
                sum_w = sum(w)
                current_weights["pods"] = round(w[0]/sum_w, 4)
                current_weights["cpu"] = round(w[1]/sum_w, 4)
                current_weights["memory"] = round(w[2]/sum_w, 4)
                current_weights["power"] = round(w[3]/sum_w, 4)
                
                # 3. Action: Deploy 50 new pods
                deploy_batch(batch, 50, ep)
                
                # --- PROFESSIONAL LOGGING TABLE ---
                print("-" * 60)
                print(f"BATCH {batch+1}/13 | TOTAL PODS: {pod_count + 50}")
                print(f"STATE:  CPU: {s_c:.2%} | MEM: {s_m:.2%} | FRAG: {s_f:.4f}")
                print(f"WEIGHTS: P:{current_weights['pods']} C:{current_weights['cpu']} M:{current_weights['memory']} W:{current_weights['power']}")
                
                time.sleep(18)
                
                # 4. Outcome AFTER decision
                _, _, r_f, r_u, r_p, r_lc, r_lm = get_live_metrics()
                
                writer.writerow([s_c, s_m, s_f, 
                                 current_weights["pods"], current_weights["cpu"], 
                                 current_weights["memory"], current_weights["power"], 
                                 r_f, r_u, r_p, r_lc, r_lm])
                f.flush()
                
                # --- RESULT LOGGING ---
                status = "✅ SUCCESS" if r_u == 0 else "❌ FAILED (UNSCHED)"
                print(f"RESULT: {status} | POWER: {r_p:.1f}W | FRAG: {r_f:.4f}")
                print("-" * 60)

    print("\n" + "="*60)
    print("✅ DATA COLLECTION COMPLETE: 'btp_perfect_dataset.csv' SAVED")
    print("="*60)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)
    start_collection(episodes=250)