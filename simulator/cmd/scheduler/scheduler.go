package main

import (
	"os"

	"k8s.io/component-base/cli"
	_ "k8s.io/component-base/logs/json/register"
	_ "k8s.io/component-base/metrics/prometheus/clientgo"
	_ "k8s.io/component-base/metrics/prometheus/version"
	"k8s.io/klog/v2"

	"sigs.k8s.io/kube-scheduler-simulator/simulator/pkg/debuggablescheduler"
	"sigs.k8s.io/kube-scheduler-simulator/simulator/scheduler/plugin/powertopsis"
)

func main() {
	// Register the custom PowerAware TOPSIS plugin
	command, cancelFn, err := debuggablescheduler.NewSchedulerCommand(
		debuggablescheduler.WithPlugin(powertopsis.Name, powertopsis.New),
	)

	if err != nil {
		klog.ErrorS(err, "failed to build the debuggablescheduler command")
		os.Exit(1)
	}

	code := cli.Run(command)
	cancelFn()
	os.Exit(code)
}