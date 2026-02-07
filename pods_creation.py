import yaml
import random
import subprocess

NUM_PODS = 200
SCHEDULER_NAME = "default-scheduler"

def create_pod(name):
    cpu_request = round(random.uniform(0.2, 2.0), 2)
    mem_request = random.randint(256, 2048)

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name},
        "spec": {
            "schedulerName": SCHEDULER_NAME,
            "containers": [
                {
                    "name": "container",
                    "image": "nginx",
                    "resources": {
                        "requests": {
                            "cpu": str(cpu_request),
                            "memory": f"{mem_request}Mi"
                        }
                    }
                }
            ]
        }
    }

pods = [create_pod(f"pod-{i}") for i in range(NUM_PODS)]

with open("pods.yaml", "w") as f:
    yaml.dump_all(pods, f)

subprocess.run([
    "kubectl",
    "--kubeconfig",
    "kubeconfig.yaml",
    "apply",
    "-f",
    "pods.yaml"
])


print("Pods created and scheduled.")
