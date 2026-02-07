import yaml
import random
import subprocess

NUM_SMALL = 10
NUM_MEDIUM = 10
NUM_LARGE = 10

NODE_TYPES = {
    "small": (2, 4),
    "medium": (8, 16),
    "large": (32, 64)
}

MEM_TYPES = {
    "small": (8, 16),
    "medium": (32, 64),
    "large": (128, 256)
}

def create_node(name, cpu, mem):
    return {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {"name": name},
        "status": {
            "capacity": {
                "cpu": str(cpu),
                "memory": f"{mem}Gi",
                "pods": "250"
            },
            "allocatable": {
                "cpu": str(cpu),
                "memory": f"{mem}Gi",
                "pods": "250"
            }
        }
    }


nodes = []

for i in range(NUM_SMALL):
    cpu = random.randint(*NODE_TYPES["small"])
    mem = random.randint(*MEM_TYPES["small"])
    nodes.append(create_node(f"small-node-{i}", cpu, mem))

for i in range(NUM_MEDIUM):
    cpu = random.randint(*NODE_TYPES["medium"])
    mem = random.randint(*MEM_TYPES["medium"])
    nodes.append(create_node(f"medium-node-{i}", cpu, mem))

for i in range(NUM_LARGE):
    cpu = random.randint(*NODE_TYPES["large"])
    mem = random.randint(*MEM_TYPES["large"])
    nodes.append(create_node(f"large-node-{i}", cpu, mem))

with open("nodes.yaml", "w") as f:
    yaml.dump_all(nodes, f)

subprocess.run([
    "kubectl",
    "--kubeconfig",
    "kubeconfig.yaml",
    "apply",
    "-f",
    "nodes.yaml"
])


print("Nodes created.")
