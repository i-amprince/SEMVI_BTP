import subprocess
import yaml
import time
import random
import numpy as np
import math
import threading
import joblib
from flask import Flask, jsonify
import logging

# --- LOAD TRAINED BRAIN ---
model = joblib.load('btp_model.pkl')

# --- CONFIG ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Global weights that the Go plugin will fetch
current_weights = {"pods": 0.25, "cpu": 0.25, "memory": 0.25, "power": 0.25}

@app.route('/get_weights', methods=['GET'])
def get_weights():
    return jsonify(current_weights)

# --- REUSE YOUR METRICS LOGIC ---
def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def parse_cpu(val):
    if not val: return 0.0
    s = str(val).strip()
    return float(s[:-1]) / 1000.0 if s.endswith('m') else float(s)

def parse_mem(val):
    if not val: return 0.0
    s = str(val).strip().replace('i', '')
    if s.endswith('G'): return float(s[:-1])
    if s.endswith('M'): return float(s[:-1]) / 1024.0
    return float(s) / (1024.0 ** 3)

def get_live_metrics():
    k_cfg = "--kubeconfig kubeconfig.yaml"
    nodes_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get nodes -o yaml"))
    pods_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get pods -o yaml"))
    if not nodes_raw or 'items' not in nodes_raw: return 0, 0, 0
    
    node_stats = {}
    c_cap_total = m_cap_total = 0.0
    for n in nodes_raw['items']:
        name = n['metadata']['name']
        alloc = n.get('status', {}).get('allocatable', n.get('status', {}).get('capacity', {}))
        c, m = parse_cpu(alloc.get('cpu', '1')), parse_mem(alloc.get('memory', '1G'))
        node_stats[name] = {'c_cap': c, 'm_cap': m, 'c_u': 0.0, 'm_u': 0.0}
        c_cap_total += c
        m_cap_total += m

    total_pods = len(pods_raw.get('items', []))
    u_count = 0
    for p in pods_raw.get('items', []):
        node = p.get('spec', {}).get('nodeName')
        if not node or node not in node_stats:
            u_count += 1
            continue
        for res in [c.get('resources', {}).get('requests', {}) for c in p['spec']['containers']]:
            node_stats[node]['c_u'] += parse_cpu(res.get('cpu', 0))
            node_stats[node]['m_u'] += parse_mem(res.get('memory', 0))

    u_ratio = u_count / total_pods if total_pods > 0 else 0.0
    c_used_total = sum(n['c_u'] for n in node_stats.values())
    m_used_total = sum(n['m_u'] for n in node_stats.values())
    
    rf_v = []
    for ns in node_stats.values():
        u = np.array([max(ns['c_cap']-ns['c_u'], 0), max(ns['m_cap']-ns['m_u'], 0)])
        v = np.array([ns['c_cap'], ns['m_cap']])
        nv = np.linalg.norm(v)
        rf_v.append((np.linalg.norm(u) / nv) * u_ratio if nv > 1e-9 else 0.0)
        
    return c_used_total/c_cap_total, m_used_total/m_cap_total, np.mean(rf_v)

# --- AI OPTIMIZATION CORE ---
def update_smart_weights():
    global current_weights
    while True:
        # 1. Get current state
        s_c, s_m, s_f = get_live_metrics()
        
        # 2. Hallucinate 100 weight possibilities
        candidates = []
        for _ in range(100):
            w = [random.uniform(0.1, 1.0) for _ in range(4)]
            sum_w = sum(w)
            candidates.append([w[0]/sum_w, w[1]/sum_w, w[2]/sum_w, w[3]/sum_w])
            
        # 3. Predict outcomes
        # Input: [s_cpu, s_mem, s_frag, w_pod, w_cpu, w_mem, w_pow]
        inputs = [[s_c, s_m, s_f] + c for c in candidates]
        preds = model.predict(inputs)
        
        # 4. Score using the Cost Function
        # target indices: 0:r_frag, 1:r_unsched, 2:r_pow
        best_score = float('inf')
        best_w = candidates[0]
        
        for i, p in enumerate(preds):
            # The Logic: Minimize Power & Frag, Penalize Unscheduled
            score = (p[1] * 10000) + (p[2] / 1000) + (p[0] * 500)
            if score < best_score:
                best_score = score
                best_w = candidates[i]
        
        # 5. Apply winning weights to the API
        current_weights = {"pods": best_w[0], "cpu": best_w[1], "memory": best_w[2], "power": best_w[3]}
        print(f"📊 State: CPU:{s_c:.2f} | AI Selected Power Weight: {current_weights['power']:.4f}")
        time.sleep(5) # Update every 5 seconds

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, use_reloader=False), daemon=True).start()
    update_smart_weights()