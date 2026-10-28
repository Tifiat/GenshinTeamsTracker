package main

import (
	"fmt"
	"io"
	"os"
	"strings"
	"testing"
	"time"
)

// The parent receives the frozen H-light result before acknowledging. Baseline
// cannot start before that parent-clock endpoint. Waiting consumes the shared
// research clock but does not touch a policy, model, cache or search parameter.
func contrastReadAck(reader io.Reader) error {
	var token string
	if _, err := fmt.Fscanln(reader, &token); err != nil {
		return err
	}
	if token != "CONTINUE_BASELINE" {
		return fmt.Errorf("unexpected prefix acknowledgment")
	}
	return nil
}

func contrastBeforeBaseline(t *testing.T) {
	t.Helper()
	at := time.Now()
	emitFeasible(map[string]any{"kind": "contrast_light_ready", "baseline_started": false})
	if err := contrastReadAck(os.Stdin); err != nil {
		t.Fatal("parent prefix acknowledgment failed", err)
	}
	emitFeasible(map[string]any{"kind": "contrast_prefix_ack", "wait_seconds": time.Since(at).Seconds()})
}

func TestContrastPrefixAcknowledgment(t *testing.T) {
	if err := contrastReadAck(strings.NewReader("CONTINUE_BASELINE\n")); err != nil {
		t.Fatal(err)
	}
	for _, input := range []string{"", "different\n", "CONTINUE_BASELINE extra\n"} {
		if err := contrastReadAck(strings.NewReader(input)); err == nil {
			t.Fatal("invalid acknowledgment accepted", input)
		}
	}
}

func TestContrastPreservesWorkAndAuditQuotas(t *testing.T) {
	config, err := commonHConfiguration("full", 946)
	if err != nil || config.CatalogPasses != 2 || config.PolicySeconds != 180 || config.FormulaLimit != 400000 || config.GradientLimit != 100000 || config.ResolveLimit != 9+16*946+64 {
		t.Fatal("Stage10 numerical work configuration changed", config, err)
	}
	if lightOverallSeconds != 240 || lightAuditSeconds != 29 || lightChecksSeconds != 12 || lightTargetSeconds != 7 || lightAttemptSeconds != 3 || lightTargetFormula != 30000 || lightTargetGradient != 7500 {
		t.Fatal("frozen contrast clocks or audit quotas changed")
	}
}
