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

# --- HETEROGENEOUS POWER PARAMETERS (Watts per Core) ---
# K0: Static power, K1: Dynamic power scaling, K2: Efficiency curve
K0, K1, K2 = 10.0, 5.0, 4.0 

# Workload Sizing (Experiment 3 Style - Heavy Workload)
CPU_MIN, CPU_MAX = 0.5, 1.5
MEM_MIN_MIB, MEM_MAX_MIB = 4096, 6144  

# --- API SERVER ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

current_weights = {"pods": 0.25, "cpu": 0.25, "memory": 0.25, "power": 0.25}

@app.route('/get_weights', methods=['GET'])
def get_weights():
    return jsonify(current_weights)

def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- UTILITIES ---
def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def parse_cpu(val):
    if not val: return 0.0
    s = str(val).strip()
    return float(s[:-1])/1000.0 if s.endswith('m') else float(s)

def parse_mem(val):
    if not val: return 0.0
    s = str(val).strip().replace('i', '')
    if s.endswith('G'): return float(s[:-1])
    if s.endswith('M'): return float(s[:-1]) / 1024.0
    return float(s)

# --- METRIC EXTRACTION (10-Point Feature Vector) ---
def get_live_metrics():
    k_cfg = "--kubeconfig kubeconfig.yaml"
    nodes_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get nodes -o yaml"))
    pods_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get pods -o yaml"))
    
    if not nodes_raw or 'items' not in nodes_raw: return [0.0]*11
        
    node_stats = {}
    for n in nodes_raw['items']:
        name = n['metadata']['name']
        alloc = n.get('status', {}).get('allocatable', n.get('status', {}).get('capacity', {}))
        node_stats[name] = {
            'cap_c': parse_cpu(alloc.get('cpu', '1')), 
            'cap_m': parse_mem(alloc.get('memory', '1G')), 
            'u_c': 0.0, 'u_m': 0.0, 'pod_count': 0
        }

    total_pods = len(pods_raw.get('items', []))
    unscheduled = sum(1 for p in pods_raw.get('items', []) if not p.get('spec', {}).get('nodeName'))
    u_ratio = unscheduled / total_pods if total_pods > 0 else 0.0

    for p in pods_raw.get('items', []):
        node_name = p.get('spec', {}).get('nodeName')
        if node_name and node_name in node_stats:

            node_stats[node_name]['pod_count'] += 1
            for container in p['spec']['containers']:
                req = container.get('resources', {}).get('requests', {})
                node_stats[node_name]['u_c'] += parse_cpu(req.get('cpu', 0))
                node_stats[node_name]['u_m'] += parse_mem(req.get('memory', 0))

    cpu_utils, mem_utils, node_frags, total_power, active_nodes = [], [], [], 0.0, 0
    for ns in node_stats.values():
        c_u = min(ns['u_c'] / ns['cap_c'], 1.0) if ns['cap_c'] > 0 else 0
        m_u = min(ns['u_m'] / ns['cap_m'], 1.0) if ns['cap_m'] > 0 else 0
        cpu_utils.append(c_u)
        mem_utils.append(m_u)
        
        if ns['pod_count'] > 0:
            active_nodes += 1
            total_power += (K0 * ns['cap_c']) + (K1 * ns['cap_c']) * (1 - math.exp(-K2 * c_u))
        
        u_vec = np.array([max(ns['cap_c'] - ns['u_c'], 0), max(ns['cap_m'] - ns['u_m'], 0)])
        v_vec = np.array([ns['cap_c'], ns['cap_m']])
        node_frags.append((np.linalg.norm(u_vec) / np.linalg.norm(v_vec)) if np.linalg.norm(v_vec) > 0 else 0)

    lbf_c = np.std(cpu_utils)/np.mean(cpu_utils) if np.mean(cpu_utils)>0 else 0
    lbf_m = np.std(mem_utils)/np.mean(mem_utils) if np.mean(mem_utils)>0 else 0
    avg_node_frag = np.mean(node_frags)
    paper_frag = avg_node_frag * u_ratio
    
    return (np.mean(cpu_utils), np.mean(mem_utils), avg_node_frag, active_nodes, 
            lbf_c, lbf_m, u_ratio, total_power, paper_frag, total_pods)

# --- COLLECTION ENGINE ---
def start_collection(episodes=100):
    global current_weights
    filename = "btp_master_full_dataset.csv"
    
    with open(filename, "a", newline="") as f:
        writer = csv.writer(f)
        # 19 COLUMNS TOTAL

        #removeeee thisss --------------------------------------------------- below uncomment it
        # writer.writerow([
        #     "s_cpu", "s_mem", "s_node_frag", "s_active", "s_lbf_c", "s_lbf_m", 
        #     "b_cpu_avg", "b_mem_avg", 
        #     "w_pod", "w_cpu", "w_mem", "w_pow", 
        #     "r_pow", "r_node_frag", "r_paper_frag", "r_unsched", "r_active", "r_lbf_c", "r_lbf_m"
        # ])

        for ep in range(episodes):
            print(f"\n🚀 Episode {ep+1}/{episodes} | Clearing Cluster...")
            run_cmd("kubectl --kubeconfig kubeconfig.yaml delete pods --all --force --grace-period=0")
            time.sleep(5) 

            for batch in range(12):
                # 1. Capture FULL State Before
                s_c, s_m, s_nf, s_a, s_lc, s_lm, _, _, _, _ = get_live_metrics()

                # 2. Extreme Weight Sampling (25% chance for dominant weights)
                if random.random() < 0.75:
                    w = [random.uniform(0.1, 1.0) for _ in range(4)]
                else:
                    w = [random.uniform(0.01, 0.1) for _ in range(4)]
                    w[random.randint(0, 3)] = random.uniform(0.7, 0.9)
                
                sum_w = sum(w)
                current_weights = {k: round(v/sum_w, 4) for k, v in zip(["pods", "cpu", "memory", "power"], w)}

                # 3. Create Pods & Track Batch Workload Stats
                pods, b_c_sum, b_m_sum = [], 0.0, 0.0
                for i in range(50):
                    c, m = round(random.uniform(CPU_MIN, CPU_MAX), 2), random.randint(MEM_MIN_MIB, MEM_MAX_MIB)
                    b_c_sum += c
                    b_m_sum += m
                    pods.append({
                        "apiVersion": "v1", "kind": "Pod", 
                        "metadata": {"name": f"e{ep}-b{batch}-p{i}"},
                        "spec": {
                            "schedulerName": "power-aware-scheduler", 
                            "restartPolicy": "Never",
                            "containers": [{
                                "name": "c", "image": "nginx:alpine",
                                "resources": {"requests": {"cpu": f"{int(c*1000)}m", "memory": f"{m}Mi"}}
                            }]
                        }
                    })
                
                with open("batch.yaml", "w") as tf: yaml.dump_all(pods, tf)
                run_cmd("kubectl --kubeconfig kubeconfig.yaml apply -f batch.yaml")
                time.sleep(18) # Wait for Go scoring cycle

                # 4. Capture FULL Outcome After
                _, _, r_nf, r_a, r_lc, r_lm, r_u, r_p, r_pf, _ = get_live_metrics()

                # 5. Write All 19 Columns
                writer.writerow([
                    round(s_c, 4), round(s_m, 4), round(s_nf, 4), s_a, round(s_lc, 4), round(s_lm, 4),
                    round(b_c_sum/50, 4), round((b_m_sum/50)/1024, 4),
                    current_weights["pods"], current_weights["cpu"], current_weights["memory"], current_weights["power"],
                    round(r_p, 2), round(r_nf, 6), round(r_pf, 6), round(r_u, 4), r_a, round(r_lc, 4), round(r_lm, 4)
                ])
                f.flush()
                print(f"Batch {batch+1} | Power: {r_p:.1f}W | LBF-M: {r_lm:.4f} | Frag: {r_nf:.4f}")

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)
    start_collection(episodes=100)