import yaml
import random
import subprocess

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE THESE TO MATCH YOUR TEST RUN
EXPERIMENT     = 3                   # 1, 2, or 3
SCHEDULER_NAME = "power-aware-scheduler" # "power-aware-scheduler" OR "default-scheduler"
# ─────────────────────────────────────────────────────────────────────────────

POD_COUNTS = {1: 100, 2: 100, 3: 500}
NUM_PODS   = POD_COUNTS[EXPERIMENT]

# Workload Sizing: Average ~2.25 Cores and ~5 GiB Mem per pod.
# This strictly enforces the 45% unscheduled ratio in Experiment 3.
CPU_MIN_CORES = 0.5
CPU_MAX_CORES = 1.5
MEM_MIN_MIB   = 4096  # 2 GiB
MEM_MAX_MIB   = 6144  # 8 GiB

def create_pod(name: str) -> dict:
    cpu = round(random.uniform(CPU_MIN_CORES, CPU_MAX_CORES), 2)
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
                    "requests": {"cpu": f"{cpu}", "memory": f"{mem}Mi"},
                    "limits":   {"cpu": f"{cpu}", "memory": f"{mem}Mi"},
                },
            }],
        },
    }

random.seed(42) # Ensure exact same pods are generated for both schedulers

pods = [create_pod(f"pod-{i}") for i in range(NUM_PODS)]

with open("pods.yaml", "w") as f:
    yaml.dump_all(pods, f, default_flow_style=False)

print(f"Running Experiment {EXPERIMENT}: Deploying {NUM_PODS} pods using '{SCHEDULER_NAME}'")

result = subprocess.run(
    ["kubectl", "--kubeconfig", "kubeconfig.yaml", "apply", "-f", "pods.yaml"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("ERROR:", result.stderr)
else:
    print("Pods applied successfully!")