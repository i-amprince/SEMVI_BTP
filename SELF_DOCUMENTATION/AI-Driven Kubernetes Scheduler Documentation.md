# ---

**Project Documentation: Power-Aware Dynamic Kubernetes Scheduler**

## **1\. Project Overview**

This project implements a multi-criteria, power-aware scheduling framework for Kubernetes. It transitions from a static TOPSIS-based scheduling plugin to a fully dynamic, AI-driven Smart Master that adjusts scheduling weights in real-time based on cluster load, effectively balancing the Pareto trade-off between power consumption and resource fragmentation.

## ---

**2\. Phase 1: Static Scheduling & Infrastructure (Pre-Midsem)**

The initial phase focused on understanding Kubernetes internals, modifying the scheduling framework, and establishing a static power-aware baseline.

* **Core TOPSIS Plugin:** Implemented in simulator/scheduler/plugin/powertopsis/plugin.go. This calculates node scores based on incoming weights for CPU, Memory, Pods, and Power.  
* **Plugin Registration:** The custom plugin is registered in the main scheduler loop at simulator/cmd/scheduler/scheduler.go.  
* **Static Configuration:** Baseline static weights are manually configured in simulator/cmd/scheduler/scheduler.yaml.  
* **Simulation & Placement:** \* Initial cluster setups were generated using node\_creation.py.  
  * Workloads were submitted using pods\_creation.py.  
  * Final cluster states were exported as YAML files via the simulator UI.  
* **Static Evaluation:** Evaluated performance differences between the Default scheduler and Static Power-Aware scheduler using check\_main.py.

**Example Evaluation Command:**

Bash

python check\_main.py \\  
  \--exp1-power power\_100.yml \--exp1-default default\_100.yml \\  
  \--exp2-power power\_300.yml \--exp2-default default\_300.yml \\  
  \--exp3-power power\_520.yml \--exp3-default default\_520.yml

## ---

**3\. Phase 2: Dynamic AI Scheduling Pipeline (Post-Midsem)**

The second phase transitioned the system to an intelligent, dynamically adapting architecture using Machine Learning.

* **Automated Data Generation:** \* Script: aimodels/automate\_datacollection.py  
  * Function: Automates the submission of varying workloads to generate the foundational btp\_master\_full\_dataset.csv.  
* **AI Model Training:** \* Scripts located in the aimodels/ directory train various regressors to predict cluster outcomes.  
  * Generates .pkl files acting as the "Brain" of the scheduler.  
* **The Smart Masters (Core Controllers):**  
  * smart\_master\_custom\_weight.py: A utility controller allowing manual injection of dynamic weights on-the-fly without needing to restart the Kubernetes scheduler.  
  * smart\_master\_power.py: The primary AI controller. It loads the .pkl models, reads live cluster state (e.g., CPU load), and dynamically serves the optimal TOPSIS weights to minimize power while maintaining stability.  
* **Automated Evaluation Pipeline:** \* Script: auto\_pods\_placement\_final.py  
  * Function: Automatically schedules batches of pods, extracts live metrics from the cluster, and saves the data to CSVs for downstream analysis.

## ---

**4\. Phase 3: Analysis & Output Directory Structure**

The evaluation and justification of the system are categorized into specific output folders.

* **ai\_models/**: Contains all model training scripts, datasets, and compiled .pkl files.  
* **model\_output/**: Contains comparative data and graphs evaluating the performance of different Machine Learning models (e.g., Decision Tree vs. XGBoost) to determine the most efficient decision engine.  
* **output\_comparisons/**: Contains the final experimental CSVs and graphs comparing the three primary systems: Default Scheduler, Static Weights, and Dynamic AI Weights.  
  * **Key Finding:** Includes the Pareto Trade-off analysis, visually proving that Power Minimization and Resource Fragmentation inherently conflict, necessitating the dynamic weight-shifting system.

## ---

**5\. Phase 4: Real-World Diurnal Simulation**

To prove commercial viability, the system is subjected to a 24-hour day/night traffic cycle simulating real-world enterprise loads.

* **Traffic Generator:** diurnal\_placement.py scales cluster workloads up during simulated "Peak Hours" and deletes workloads during "Off-Peak" hours.  
* **Data Storage:** Results for Default, Static, and Dynamic runs are saved to the diurnal/ folder.  
* **Visualization:** diurnal\_graph.py (located in the diurnal/ folder) generates the final dual-axis time-series graph. This visual proves the AI actively tracks traffic patterns, maintaining stability during the day and aggressively slashing power consumption at night.