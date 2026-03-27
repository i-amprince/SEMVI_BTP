import yaml
import random
import subprocess
import sys

# ─────────────────────────────────────────────────────────────────────────────
# We permanently set this to your custom scheduler for the ML dataset
SCHEDULER_NAME = "default-scheduler" 
# ─────────────────────────────────────────────────────────────────────────────

# --- DYNAMIC ARGUMENT INJECTION ---
# If the master script says `python pods_creation.py 350`, this grabs the "350"
if len(sys.argv) > 1:
    NUM_PODS = int(sys.argv[1])
else:
    NUM_PODS = 300 # Fallback if you run it manually without a number

# Workload Sizing: Randomizing sizes
CPU_MIN_CORES = 0.5
CPU_MAX_CORES = 1.5
MEM_MIN_MIB   = 4096  # 2 GiB
MEM_MAX_MIB   = 6144  # 8 GiB

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

# NOTICE: random.seed(42) is completely deleted. We want true randomness now!
random.seed(42)
pods = [create_pod(f"pod-{i}") for i in range(NUM_PODS)]

with open("pods.yaml", "w") as f:
    yaml.dump_all(pods, f, default_flow_style=False)

print(f"Deploying {NUM_PODS} completely random pods using '{SCHEDULER_NAME}'")

result = subprocess.run(
    ["kubectl", "--kubeconfig", "kubeconfig.yaml", "apply", "-f", "pods.yaml"],
    capture_output=True, text=True,
)

if result.returncode != 0:
    print("ERROR:", result.stderr)
else:
    print("Pods applied successfully!")