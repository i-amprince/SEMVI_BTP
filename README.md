
# ⚡ PowerAware Kubernetes Scheduler (TOPSIS-Based)

A custom Kubernetes Scheduler Plugin that integrates **power-awareness** into pod placement using **Multi-Criteria Decision Making (TOPSIS)**.

This scheduler optimizes:

- Load balancing  
- Bin packing  
- Power consumption  

Based on:

> Gouaouri et al., *Enabling power-awareness for Kubernetes scheduling through multi-criteria optimization*, IEEE ICC 2025.

---

## 📌 Problem Statement

The default Kubernetes scheduler primarily focuses on CPU and memory utilization.  
It does not explicitly optimize power consumption.

This project introduces a custom scheduler plugin that integrates energy-awareness directly into Kubernetes scoring.

---

## 🧠 Methodology

The scheduler uses the **TOPSIS algorithm** (Technique for Order of Preference by Similarity to Ideal Solution).

### Criteria Used

| Criteria | Type     | Purpose |
|----------|----------|----------|
| pods     | Benefit  | Encourage bin packing |
| cpu      | Benefit  | Prefer higher utilization |
| memory   | Benefit  | Prefer higher utilization |
| power    | Cost     | Minimize power consumption |

---

## 🔋 Power Model

Power is estimated using:

```
P(u) = k0 + k1 * (1 - e^(-k2 * u))
```

Where:

- `u` = CPU utilization  
- `k0` = baseline power  
- `k1` = additional power scaling  
- `k2` = exponential growth factor  

---

## 🏗 Modified Files

```
simulator/scheduler/plugin/powertopsis/plugin.go
simulator/cmd/scheduler/main.go
scheduler.yaml
```

---

## 🐳 Setup Instructions

### 1️⃣ Clone kube-scheduler-simulator

```bash
git clone https://github.com/kubernetes-sigs/kube-scheduler-simulator
cd kube-scheduler-simulator
```

### 2️⃣ Replace / Modify Files

Replace the modified files listed above with your implementation.

### 3️⃣ Build Docker Images

```bash
docker build -f simulator/cmd/simulator/Dockerfile -t simulator-server simulator
docker build -f simulator/cmd/scheduler/Dockerfile -t simulator-scheduler simulator
docker build -t simulator-frontend ./web
```

### 4️⃣ Run Simulator

```bash
docker compose -f compose.yml -f compose.local.yml up -d
```

---

## 🔧 Scheduler Configuration (scheduler.yaml)

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration

profiles:
  - schedulerName: default-scheduler
    plugins:
      filter:
        enabled:
          - name: "NodeResourcesFit"
          - name: "NodeName"
          - name: "NodeUnschedulable"
          - name: "TaintToleration"
      preScore:
        enabled:
          - name: "PowerAware"
      score:
        enabled:
          - name: "PowerAware"
            weight: 1
        disabled:
          - name: "*"

    pluginConfig:
      - name: PowerAware
        args:
          kind: PowerAwareArgs
          apiVersion: kubescheduler.config.k8s.io/v1

          podLoadBalancingCriteria: { weight: 0.1, type: "Benefit" }
          cpuCriteria:              { weight: 0.35, type: "Benefit" }
          memCriteria:              { weight: 0.35, type: "Benefit" }
          powerCriteria:            { weight: 0.2, type: "Cost" }

          powerModel:
            k0: 150.0
            k1: 100.0
            k2: 4.5
```

---

## 🧪 Testing with kube-scheduler-simulator

### Create kubeconfig.yaml

```yaml
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: http://localhost:3131
    insecure-skip-tls-verify: true
  name: simulator
contexts:
- context:
    cluster: simulator
    user: simulator
  name: simulator-context
current-context: simulator-context
users:
- name: simulator
  user: {}
```

### Apply Nodes

```bash
kubectl --kubeconfig ./kubeconfig.yaml apply -f nodes.yaml
```

### Apply Pods

```bash
kubectl --kubeconfig ./kubeconfig.yaml apply -f pods.yaml
```

### Delete All Pods

```bash
kubectl --kubeconfig ./kubeconfig.yaml delete pods --all
```

---

## 📊 Evaluation Metrics

### Load Balancing Factor

```
LBF = σ(R) / μ(R)
```

Lower value indicates better balance.

### Pod Count Load Balancing

```
LBFpod = σ(P) / μ(P)
```

### Resource Fragmentation

```
RF = (||unused|| / ||total||) * unschedulable_ratio
```

Lower value indicates better resource utilization.

---

## 🧪 Experiments

| Experiment | Nodes | Pods |
|------------|--------|------|
| Exp 1 | 10 | 100 |
| Exp 2 | 30 | 100 |
| Exp 3 | 30 | 500 |

Results demonstrate significant power reduction (up to ~34%) while maintaining effective workload distribution.

---

## 🚀 Key Features

- Multi-criteria TOPSIS ranking  
- Power-aware scheduling  
- Configurable weights  
- Benefit / Cost criteria support  
- Docker-based deployment  
- Compatible with kube-scheduler-simulator  

---

## 👨‍💻 Author

Prince Goyal  
B.Tech CSE  
IIIT Guwahati
