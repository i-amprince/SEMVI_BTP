package powertopsis

import (
	"context"
	"math"
	"strings"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/kubernetes/pkg/scheduler/framework"
	frameworkruntime "k8s.io/kubernetes/pkg/scheduler/framework/runtime"
)

const (
	Name             = "PowerAware"
	preScoreStateKey = "PreScore" + Name
)

type PowerAware struct {
	weights      map[string]float64
	costCriteria map[string]bool
	powerModel   PowerModelArgs
}

var (
	_ framework.PreScorePlugin = &PowerAware{}
	_ framework.ScorePlugin    = &PowerAware{}
)

type nodeVector struct {
	pods, cpu, mem, power float64
}

type preScoreState struct {
	scores map[string]int64
}

func (s *preScoreState) Clone() framework.StateData { return s }
func (pl *PowerAware) Name() string { return Name }

func (pl *PowerAware) PreScore(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodes []*framework.NodeInfo) *framework.Status {
	if len(nodes) == 0 {
		return nil
	}

	// 1. Calculate the resource requirements of the incoming pod
	// We need to know "If I put the pod here, what is the NEW utilization?"
	podCPU := int64(0)
	podMem := int64(0)
	for _, c := range pod.Spec.Containers {
		podCPU += c.Resources.Requests.Cpu().MilliValue()
		podMem += c.Resources.Requests.Memory().Value()
	}

	rawValues := make(map[string]nodeVector)
	var sumP, sumC, sumM, sumPow float64

	// 2. Build the Decision Matrix based on PREDICTED state
	for _, n := range nodes {
		// Prefer nodes with more pods (Bin Packing)
		// We add +1 to simulate the state after placement
		p := float64(len(n.Pods) + 1)

		c := 0.0
		if n.Allocatable.MilliCPU > 0 {
			// (Current Usage + New Pod Request) / Allocatable
			c = float64(n.Requested.MilliCPU+podCPU) / float64(n.Allocatable.MilliCPU)
		}

		m := 0.0
		if n.Allocatable.Memory > 0 {
			// (Current Usage + New Pod Request) / Allocatable
			m = float64(n.Requested.Memory+podMem) / float64(n.Allocatable.Memory)
		}

		// Estimate power based on the NEW CPU utilization
		pow := pl.powerModel.Estimate(c)

		rawValues[n.Node().Name] = nodeVector{pods: p, cpu: c, mem: m, power: pow}
		
		// Accumulate squares for Vector Normalization
		sumP += p * p
		sumC += c * c
		sumM += m * m
		sumPow += pow * pow
	}

	denoms := nodeVector{math.Sqrt(sumP), math.Sqrt(sumC), math.Sqrt(sumM), math.Sqrt(sumPow)}
	weightedMatrix := make(map[string]nodeVector)
	ideal := nodeVector{}
	negative := nodeVector{}
	first := true

	// 3. Normalize and Weight the Matrix
	for name, v := range rawValues {
		weighted := nodeVector{
			pods:  safeDiv(v.pods, denoms.pods) * pl.weights["pods"],
			cpu:   safeDiv(v.cpu, denoms.cpu) * pl.weights["cpu"],
			mem:   safeDiv(v.mem, denoms.mem) * pl.weights["memory"],
			power: safeDiv(v.power, denoms.power) * pl.weights["power"],
		}
		weightedMatrix[name] = weighted
		
		if first {
			ideal, negative = weighted, weighted
			first = false
		} else {
			ideal = pl.getExtreme(ideal, weighted, true)
			negative = pl.getExtreme(negative, weighted, false)
		}
	}

	// 4. Calculate Distance and Score
	scores := make(map[string]int64)
	for name, v := range weightedMatrix {
		dPlus := euclideanDist(v, ideal)
		dMinus := euclideanDist(v, negative)

		// Calculate Closeness Coefficient (C*)
		closeness := 0.5
		if (dPlus + dMinus) > 1e-9 {
			closeness = dMinus / (dPlus + dMinus)
		}
		
		// Map 0.0-1.0 to 0-100 (MaxNodeScore)
		scores[name] = int64(math.Round(closeness * float64(framework.MaxNodeScore)))
	}

	state.Write(preScoreStateKey, &preScoreState{scores: scores})
	return nil
}

func (pl *PowerAware) Score(ctx context.Context, state *framework.CycleState, pod *v1.Pod, nodeName string) (int64, *framework.Status) {
	data, err := state.Read(preScoreStateKey)
	if err != nil {
		return 0, nil
	}
	s := data.(*preScoreState)
	return s.scores[nodeName], nil
}

func (pl *PowerAware) ScoreExtensions() framework.ScoreExtensions { return nil }

// getExtreme finds the Ideal (Best) or Negative-Ideal (Worst) value for each criteria
func (pl *PowerAware) getExtreme(curr, next nodeVector, isIdeal bool) nodeVector {
	res := curr
	keys := []string{"pods", "cpu", "memory", "power"}
	for _, k := range keys {
		v := pl.getVal(next, k)
		c := pl.getVal(curr, k)
		isCost := pl.costCriteria[k]
		
		update := false
		if isIdeal {
			// For Ideal: Maximize Benefit, Minimize Cost
			if (isCost && v < c) || (!isCost && v > c) {
				update = true
			}
		} else {
			// For Negative Ideal: Minimize Benefit, Maximize Cost
			if (isCost && v > c) || (!isCost && v < c) {
				update = true
			}
		}
		if update {
			pl.setVal(&res, k, v)
		}
	}
	return res
}

func safeDiv(n, d float64) float64 {
	if d < 1e-9 {
		return 0
	}
	return n / d
}

func euclideanDist(a, b nodeVector) float64 {
	return math.Sqrt(
		math.Pow(a.pods-b.pods, 2) +
		math.Pow(a.cpu-b.cpu, 2) +
		math.Pow(a.mem-b.mem, 2) +
		math.Pow(a.power-b.power, 2),
	)
}

func (pl *PowerAware) getVal(v nodeVector, k string) float64 {
	switch k {
	case "pods": return v.pods
	case "cpu": return v.cpu
	case "memory": return v.mem
	case "power": return v.power
	}
	return 0
}

func (pl *PowerAware) setV(v *nodeVector, k string, val float64) {
	switch k {
	case "pods": v.pods = val
	case "cpu": v.cpu = val
	case "memory": v.mem = val
	case "power": v.power = val
	}
}

func (pl *PowerAware) setVal(v *nodeVector, k string, val float64) { pl.setV(v, k, val) }

type PowerModelArgs struct {
	K0 float64 `json:"k0"`
	K1 float64 `json:"k1"`
	K2 float64 `json:"k2"`
}

func (p PowerModelArgs) Estimate(x float64) float64 {
	// P(u) = k0 + k1 * (1 - e^(-k2 * u))
	return p.K0 + p.K1*(1.0-math.Exp(-p.K2*x))
}

type CriteriaConfig struct {
	Weight float64 `json:"weight"`
	Type   string  `json:"type"`
}

type PowerAwareArgs struct {
	metav1.TypeMeta          `json:",inline"`
	PodLoadBalancingCriteria CriteriaConfig `json:"podLoadBalancingCriteria"`
	CpuCriteria              CriteriaConfig `json:"cpuCriteria"`
	MemCriteria              CriteriaConfig `json:"memCriteria"`
	PowerCriteria            CriteriaConfig `json:"powerCriteria"`
	PowerModel               PowerModelArgs `json:"powerModel"`
}

func New(ctx context.Context, arg runtime.Object, h framework.Handle) (framework.Plugin, error) {
	// 1. Defaults configured for BIN PACKING (Power Saving)
	// Benefit = Maximize usage (Pack nodes)
	// Cost = Minimize power
	typedArg := PowerAwareArgs{
		// Prefer nodes with MORE pods (Benefit)
		PodLoadBalancingCriteria: CriteriaConfig{Weight: 0.1, Type: "Benefit"}, 
		// Prefer nodes with HIGHER CPU usage (Benefit)
		CpuCriteria:              CriteriaConfig{Weight: 0.35, Type: "Benefit"},
		// Prefer nodes with HIGHER Memory usage (Benefit)
		MemCriteria:              CriteriaConfig{Weight: 0.35, Type: "Benefit"},
		// Prefer nodes with LOWER Power (Cost)
		// Note: Weight must be lower than CPU+Mem benefit to prevent selecting empty nodes
		PowerCriteria:            CriteriaConfig{Weight: 0.2, Type: "Cost"},
		
		PowerModel:               PowerModelArgs{K0: 150, K1: 100, K2: 3},
	}

	// 2. Decode from YAML (if provided)
	if arg != nil {
		_ = frameworkruntime.DecodeInto(arg, &typedArg)
	}

	costMap := make(map[string]bool)
	weights := make(map[string]float64)

	// Helper to determine if a criteria is Cost (Minimize) or Benefit (Maximize)
	assign := func(k string, c CriteriaConfig) {
		weights[k] = c.Weight
		// If explicit "Benefit", set cost=false. Otherwise default to cost=true for safety 
		// unless we explicitly want defaults handled differently.
		// Here: "Cost" = true (Minimize), "Benefit" = false (Maximize)
		if strings.EqualFold(c.Type, "benefit") {
			costMap[k] = false
		} else {
			costMap[k] = true
		}
	}

	assign("pods", typedArg.PodLoadBalancingCriteria)
	assign("cpu", typedArg.CpuCriteria)
	assign("memory", typedArg.MemCriteria)
	assign("power", typedArg.PowerCriteria)

	return &PowerAware{
		weights:      weights,
		costCriteria: costMap,
		powerModel:   typedArg.PowerModel,
	}, nil
}