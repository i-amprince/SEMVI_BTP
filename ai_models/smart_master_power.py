import subprocess, yaml, time, threading, math
import numpy as np
import pandas as pd
from flask import Flask, jsonify
import joblib
import logging

# --- CONSTANTS ---
K0, K1, K2 = 10.0, 5.0, 4.0 
# Pointing to the NEW Dual-Objective Model
MODEL_FILE = "btp_xgboost_brain.pkl" 

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

current_weights = {"pods": 0.25, "cpu": 0.25, "memory": 0.25, "power": 0.25}

try:
    ai_model = joblib.load(MODEL_FILE)
    print(f"✅ Successfully loaded DUAL-OBJECTIVE AI Brain: {MODEL_FILE}")
except FileNotFoundError:
    print(f"❌ Could not find {MODEL_FILE}. Run train_model.py first!")
    exit()

@app.route('/get_weights', methods=['GET'])
def get_weights():
    return jsonify(current_weights)

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

def get_cluster_state():
    k_cfg = "--kubeconfig ../kubeconfig.yaml"
    n_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get nodes -o yaml"))
    if not n_raw or 'items' not in n_raw: return None
    
    node_stats = {}
    for n in n_raw['items']:
        name = n['metadata']['name']
        alloc = n.get('status', {}).get('allocatable', n.get('status', {}).get('capacity', {}))
        node_stats[name] = {'cap_c': parse_cpu(alloc.get('cpu', '1')), 'cap_m': parse_mem(alloc.get('memory', '1G')), 'u_c': 0.0, 'u_m': 0.0}

    p_raw = yaml.safe_load(run_cmd(f"kubectl {k_cfg} get pods -o yaml"))
    for p in p_raw.get('items', []):
        node_name = p.get('spec', {}).get('nodeName')
        if node_name and node_name in node_stats:
            for c in p['spec']['containers']:
                req = c.get('resources', {}).get('requests', {})
                node_stats[node_name]['u_c'] += parse_cpu(req.get('cpu', 0))
                node_stats[node_name]['u_m'] += parse_mem(req.get('memory', 0))

    cpu_u, mem_u, n_frags, active = [], [], [], 0
    for ns in node_stats.values():
        c_u, m_u = min(ns['u_c']/ns['cap_c'], 1.0) if ns['cap_c']>0 else 0, min(ns['u_m']/ns['cap_m'], 1.0) if ns['cap_m']>0 else 0
        cpu_u.append(c_u); mem_u.append(m_u)
        if ns['u_c'] > 0 or ns['u_m'] > 0: active += 1
        
        u_vec = np.array([max(ns['cap_c'] - ns['u_c'], 0), max(ns['cap_m'] - ns['u_m'], 0)])
        v_vec = np.array([ns['cap_c'], ns['cap_m']])
        n_frags.append((np.linalg.norm(u_vec)/np.linalg.norm(v_vec)) if np.linalg.norm(v_vec)>0 else 0)

    return {
        's_cpu': np.mean(cpu_u), 's_mem': np.mean(mem_u), 
        's_node_frag': np.mean(n_frags), 's_active': active, 
        's_lbf_c': np.std(cpu_u)/np.mean(cpu_u) if np.mean(cpu_u)>0 else 0, 
        's_lbf_m': np.std(mem_u)/np.mean(mem_u) if np.mean(mem_u)>0 else 0,
        'b_cpu_avg': 1.0, 'b_mem_avg': 5.0 
    }

import math

def ai_control_loop():
    global current_weights
    print("🚀 POWER-ONLY Control Loop Active (Baseline Testing)...")
    
    while True:
        try:
            state = get_cluster_state()
            if not state:
                time.sleep(10)
                continue
            
            candidate_weights = np.random.dirichlet(np.ones(4), size=500)
            
            best_score = float('inf')
            best_w = current_weights
            expected_pow = 0
            
            cluster_load = state['s_cpu']
            
            for w in candidate_weights:
                test_input = pd.DataFrame([{
                    **state, 
                    'w_pod': w[0], 'w_cpu': w[1], 'w_mem': w[2], 'w_pow': w[3]
                }])
                
                # Single-Objective Models only return ONE prediction: [Power]
                pred_pow = ai_model.predict(test_input)[0]
                
                # The score is purely the predicted power. We want the lowest wattage.
                score = pred_pow
                
                if score < best_score:
                    best_score = score
                    expected_pow = pred_pow
                    best_w = {"pods": round(w[0],4), "cpu": round(w[1],4), "memory": round(w[2],4), "power": round(w[3],4)}
            
            current_weights = best_w
            print(f"[{time.strftime('%H:%M:%S')}] Load: {cluster_load*100:.1f}% | Target Power: {expected_pow:.0f}W | W: {current_weights}")
            
        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=ai_control_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)