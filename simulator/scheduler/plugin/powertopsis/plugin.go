package powertopsis

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"strings"
	"time"

	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/kubernetes/pkg/scheduler/framework"
	frameworkruntime "k8s.io/kubernetes/pkg/scheduler/framework/runtime"
)

func (pl *PowerAware) ScoreExtensions() framework.ScoreExtensions {
	return nil
}

const (
	Name             = "PowerAware"
	preScoreStateKey = "PreScore" + Name
)

type PowerModelArgs struct {
	K0 float64 `json:"k0"`
	K1 float64 `json:"k1"`
	K2 float64 `json:"k2"`
}

// Estimate now scales the baseline power by the number of CPU cores
func (p PowerModelArgs) Estimate(x float64, cores float64) float64 {
	nodeK0 := p.K0 * cores
	nodeK1 := p.K1 * cores
	return nodeK0 + nodeK1*(1.0-math.Exp(-p.K2*x))
}

type CriteriaConfig struct {
	Weight float64 `json:"weight"`
	Type   string  `json:"type"`
}

type PowerAwareArgs struct {
	PodLoadBalancingCriteria CriteriaConfig `json:"podLoadBalancingCriteria"`
	CpuCriteria              CriteriaConfig `json:"cpuCriteria"`
	MemCriteria              CriteriaConfig `json:"memCriteria"`
	PowerCriteria            CriteriaConfig `json:"powerCriteria"`
	PowerModel               PowerModelArgs `json:"powerModel"`
}

type PowerAware struct {
	handle       framework.Handle
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

	// ========================================================================
	// NEW: DYNAMIC API WEIGHT FETCHING
	// Pings the Python ML server for real-time weights. 
	// Uses a 2-second timeout so the scheduler doesn't break if Python is offline.
	// ========================================================================
	client := http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://localhost:5000/get_weights")
	if err == nil {
		defer resp.Body.Close()
		var apiWeights map[string]float64
		// If Python replies with new weights, temporarily override the YAML weights for this scheduling cycle
		if err := json.NewDecoder(resp.Body).Decode(&apiWeights); err == nil {
			if w, ok := apiWeights["pods"]; ok {
				pl.weights["pods"] = w
			}
			if w, ok := apiWeights["cpu"]; ok {
				pl.weights["cpu"] = w
			}
			if w, ok := apiWeights["memory"]; ok {
				pl.weights["memory"] = w
			}
			if w, ok := apiWeights["power"]; ok {
				pl.weights["power"] = w
			}
		}
	}
	// ========================================================================

	rawValues := make(map[string]nodeVector, len(nodes))
	var sumP, sumC, sumM, sumPow float64

	for _, n := range nodes {
		nodeName := n.Node().Name

		p := float64(len(n.Pods)+1) / 110.0

		utilCPU := float64(n.Requested.MilliCPU) / float64(n.Allocatable.MilliCPU)
		utilMem := float64(n.Requested.Memory) / float64(n.Allocatable.Memory)

		c := 1.0 - utilCPU
		m := 1.0 - utilMem

		// Extract total cores for heterogeneous power scaling
		totalCores := float64(n.Allocatable.MilliCPU) / 1000.0
		if totalCores <= 0 {
			totalCores = 1.0
		}

		pow := pl.powerModel.Estimate(math.Min(utilCPU, 1.0), totalCores)

		rawValues[nodeName] = nodeVector{pods: p, cpu: c, mem: m, power: pow}
		sumP += p * p
		sumC += c * c
		sumM += m * m
		sumPow += pow * pow
	}

	denoms := nodeVector{
		pods:  math.Sqrt(sumP) + 1e-9,
		cpu:   math.Sqrt(sumC) + 1e-9,
		mem:   math.Sqrt(sumM) + 1e-9,
		power: math.Sqrt(sumPow) + 1e-9,
	}

	weightedMatrix := make(map[string]nodeVector, len(nodes))
	var ideal, negative nodeVector
	first := true

	for name, v := range rawValues {
		weighted := nodeVector{
			pods:  (v.pods / denoms.pods) * pl.weights["pods"],
			cpu:   (v.cpu / denoms.cpu) * pl.weights["cpu"],
			mem:   (v.mem / denoms.mem) * pl.weights["memory"],
			power: (v.power / denoms.power) * pl.weights["power"],
		}
		weightedMatrix[name] = weighted

		if first {
			ideal, negative, first = weighted, weighted, false
		} else {
			ideal = pl.getExtreme(ideal, weighted, true)
			negative = pl.getExtreme(negative, weighted, false)
		}
	}

	scores := make(map[string]int64, len(nodes))
	for name, v := range weightedMatrix {
		dPlus := math.Sqrt(math.Pow(v.pods-ideal.pods, 2) + math.Pow(v.cpu-ideal.cpu, 2) + math.Pow(v.mem-ideal.mem, 2) + math.Pow(v.power-ideal.power, 2))
		dMinus := math.Sqrt(math.Pow(v.pods-negative.pods, 2) + math.Pow(v.cpu-negative.cpu, 2) + math.Pow(v.mem-negative.mem, 2) + math.Pow(v.power-negative.power, 2))

		closeness := 0.0
		if (dPlus + dMinus) > 1e-9 {
			closeness = dMinus / (dPlus + dMinus)
		}

		score := int64(math.Round(closeness * float64(framework.MaxNodeScore)))
		if score > framework.MaxNodeScore {
			score = framework.MaxNodeScore
		}
		if score < framework.MinNodeScore {
			score = framework.MinNodeScore
		}
		scores[name] = score
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

func (pl *PowerAware) getExtreme(curr, next nodeVector, isIdeal bool) nodeVector {
	res := curr
	keys := []string{"pods", "cpu", "memory", "power"}

	for _, k := range keys {
		v, c := pl.getVal(next, k), pl.getVal(curr, k)
		isCost := pl.costCriteria[k]

		var shouldUpdate bool
		if isIdeal {
			shouldUpdate = (isCost && v < c) || (!isCost && v > c)
		} else {
			shouldUpdate = (isCost && v > c) || (!isCost && v < c)
		}

		if shouldUpdate {
			pl.setVal(&res, k, v)
		}
	}
	return res
}

func (pl *PowerAware) getVal(v nodeVector, k string) float64 {
	switch k {
	case "pods":
		return v.pods
	case "cpu":
		return v.cpu
	case "memory":
		return v.mem
	case "power":
		return v.power
	}
	return 0
}

func (pl *PowerAware) setVal(v *nodeVector, k string, val float64) {
	switch k {
	case "pods":
		v.pods = val
	case "cpu":
		v.cpu = val
	case "memory":
		v.mem = val
	case "power":
		v.power = val
	}
}

func New(ctx context.Context, arg runtime.Object, h framework.Handle) (framework.Plugin, error) {
	args := PowerAwareArgs{}
	if err := frameworkruntime.DecodeInto(arg, &args); err != nil {
		return nil, err
	}

	costMap := map[string]bool{
		"pods":   strings.EqualFold(args.PodLoadBalancingCriteria.Type, "Cost"),
		"cpu":    strings.EqualFold(args.CpuCriteria.Type, "Cost"),
		"memory": strings.EqualFold(args.MemCriteria.Type, "Cost"),
		"power":  strings.EqualFold(args.PowerCriteria.Type, "Cost"),
	}
	weights := map[string]float64{
		"pods":   args.PodLoadBalancingCriteria.Weight,
		"cpu":    args.CpuCriteria.Weight,
		"memory": args.MemCriteria.Weight,
		"power":  args.PowerCriteria.Weight,
	}

	return &PowerAware{
		handle:       h,
		weights:      weights,
		costCriteria: costMap,
		powerModel:   args.PowerModel,
	}, nil
}