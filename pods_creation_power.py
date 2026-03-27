import yaml
import random
import subprocess
import sys

SCHEDULER_NAME = "power-aware-scheduler" 

if len(sys.argv) > 1:
    NUM_PODS = int(sys.argv[1])
else:
    NUM_PODS = 300

CPU_MIN_CORES = 0.5
CPU_MAX_CORES = 1.5
MEM_MIN_MIB   = 4096
MEM_MAX_MIB   = 6144

def create_pod(name: str) -> dict:
    cpu_cores = round(random.uniform(CPU_MIN_CORES, CPU_MAX_CORES), 2)
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
                    "requests": {"cpu": f"{cpu_cores}m", "memory": f"{mem}Mi"},
                    "limits":   {"cpu": f"{cpu_cores}m", "memory": f"{mem}Mi"},
                },
            }],
        },
    }

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