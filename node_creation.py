import yaml
import random
import subprocess

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE THIS TO MATCH YOUR EXPERIMENT (1, 2, or 3)
EXPERIMENT = 1
# ─────────────────────────────────────────────────────────────────────────────

# Setup node distribution to ensure math aligns with paper's unscheduled ratios
if EXPERIMENT == 1:
    # 10 Nodes total (Capacity: ~246 Cores). 
    # Fits exactly 100 pods (225 cores) with 0 unscheduled.
    NUM_SMALL  = 2
    NUM_MEDIUM = 4
    NUM_LARGE  = 4
else:
    # 30 Nodes total (Capacity: ~630 Cores). 
    # Fits 100 pods easily (Exp 2). 
    # Overloads at ~280 pods during the 500 pod test (Exp 3) giving ~45% unscheduled.
    NUM_SMALL  = 10
    NUM_MEDIUM = 10
    NUM_LARGE  = 10

# Paper Table I specifications
NODE_CPU = {
    "small":  (2,   4),
    "medium": (8,  16),
    "large":  (32, 64),
}
NODE_MEM_GIB = {
    "small":  (8,   16),
    "medium": (32,  64),
    "large":  (128, 256),
}

MAX_PODS = 110 # Kubernetes standard default

def create_node(name: str, cpu: int, mem_gib: int) -> dict:
    capacity = {
        "cpu":    str(cpu),
        "memory": f"{mem_gib}Gi",
        "pods":   str(MAX_PODS),
    }
    return {
        "apiVersion": "v1",
        "kind":       "Node",
        "metadata":   {
            "name": name,
            "namespace": "default",  # explicit
        },
        "status": {
            "capacity":    capacity,
            "allocatable": capacity,
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }

random.seed(42) # Reproducibility
nodes = []

for i in range(NUM_SMALL):
    cpu = random.randint(*NODE_CPU["small"])
    mem = random.randint(*NODE_MEM_GIB["small"])
    nodes.append(create_node(f"small-node-{i}", cpu, mem))

for i in range(NUM_MEDIUM):
    cpu = random.randint(*NODE_CPU["medium"])
    mem = random.randint(*NODE_MEM_GIB["medium"])
    nodes.append(create_node(f"medium-node-{i}", cpu, mem))

for i in range(NUM_LARGE):
    cpu = random.randint(*NODE_CPU["large"])
    mem = random.randint(*NODE_MEM_GIB["large"])
    nodes.append(create_node(f"large-node-{i}", cpu, mem))

with open("nodes.yaml", "w") as f:
    yaml.dump_all(nodes, f, default_flow_style=False)

print(f"Created {len(nodes)} nodes ({NUM_SMALL} small, {NUM_MEDIUM} medium, {NUM_LARGE} large).")

result = subprocess.run(
    ["kubectl", "--kubeconfig", "kubeconfig.yaml", "apply", "-f", "nodes.yaml"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("ERROR:", result.stderr)
else:
    print("Nodes applied successfully!")