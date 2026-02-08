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
func (pl *PowerAware) Name() string                 { return Name }

func (pl *PowerAware) PreScore(
	ctx context.Context,
	state *framework.CycleState,
	pod *v1.Pod,
	nodes []*framework.NodeInfo,
) *framework.Status {

	if len(nodes) == 0 {
		return nil
	}

	rawValues := make(map[string]nodeVector)
	var sumP, sumC, sumM, sumPow float64

	for _, n := range nodes {

		// EXACT paper logic: use CURRENT state only
		p := float64(len(n.Pods))

		c := 0.0
		if n.Allocatable.MilliCPU > 0 {
			c = float64(n.Requested.MilliCPU) / float64(n.Allocatable.MilliCPU)
		}

		m := 0.0
		if n.Allocatable.Memory > 0 {
			m = float64(n.Requested.Memory) / float64(n.Allocatable.Memory)
		}

		// EXACT paper power formula
		pow := pl.powerModel.Estimate(c)

		rawValues[n.Node().Name] = nodeVector{
			pods:  p,
			cpu:   c,
			mem:   m,
			power: pow,
		}

		sumP += p * p
		sumC += c * c
		sumM += m * m
		sumPow += pow * pow
	}

	denoms := nodeVector{
		math.Sqrt(sumP),
		math.Sqrt(sumC),
		math.Sqrt(sumM),
		math.Sqrt(sumPow),
	}

	weightedMatrix := make(map[string]nodeVector)
	ideal := nodeVector{}
	negative := nodeVector{}
	first := true

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

	scores := make(map[string]int64)

	for name, v := range weightedMatrix {

		dPlus := euclideanDist(v, ideal)
		dMinus := euclideanDist(v, negative)

		closeness := 0.5
		if (dPlus + dMinus) > 1e-9 {
			closeness = dMinus / (dPlus + dMinus)
		}

		scores[name] = int64(math.Round(closeness * float64(framework.MaxNodeScore)))
	}

	state.Write(preScoreStateKey, &preScoreState{scores: scores})
	return nil
}

func (pl *PowerAware) Score(
	ctx context.Context,
	state *framework.CycleState,
	pod *v1.Pod,
	nodeName string,
) (int64, *framework.Status) {

	data, err := state.Read(preScoreStateKey)
	if err != nil {
		return 0, nil
	}

	s := data.(*preScoreState)
	return s.scores[nodeName], nil
}

func (pl *PowerAware) ScoreExtensions() framework.ScoreExtensions {
	return nil
}

func (pl *PowerAware) getExtreme(curr, next nodeVector, isIdeal bool) nodeVector {

	res := curr
	keys := []string{"pods", "cpu", "memory", "power"}

	for _, k := range keys {

		v := pl.getVal(next, k)
		c := pl.getVal(curr, k)
		isCost := pl.costCriteria[k]

		update := false

		if isIdeal {
			if (isCost && v < c) || (!isCost && v > c) {
				update = true
			}
		} else {
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

type PowerModelArgs struct {
	K0 float64 `json:"k0"`
	K1 float64 `json:"k1"`
	K2 float64 `json:"k2"`
}

// EXACT paper formula: P(x) = k0 + k1 * exp(-k2 * x)
func (p PowerModelArgs) Estimate(x float64) float64 {
	return p.K0 + p.K1*math.Exp(-p.K2*x)
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

	typedArg := PowerAwareArgs{
		PodLoadBalancingCriteria: CriteriaConfig{Weight: 0.2, Type: "Cost"},
		CpuCriteria:              CriteriaConfig{Weight: 0.2, Type: "Cost"},
		MemCriteria:              CriteriaConfig{Weight: 0.2, Type: "Cost"},
		PowerCriteria:            CriteriaConfig{Weight: 0.4, Type: "Cost"},
		PowerModel:               PowerModelArgs{K0: 150, K1: 100, K2: 3},
	}

	if arg != nil {
		_ = frameworkruntime.DecodeInto(arg, &typedArg)
	}

	costMap := make(map[string]bool)
	weights := make(map[string]float64)

	assign := func(k string, c CriteriaConfig) {
		weights[k] = c.Weight
		costMap[k] = strings.EqualFold(c.Type, "Cost")
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
