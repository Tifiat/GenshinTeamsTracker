package main

import (
	"context"
	"testing"
)

func TestProductNoDeadlineAndExplicitDiagnosticDeadline(t *testing.T) {
	for _, ms := range []int64{0, 3000} {
		ctx, cancel := productContext(context.Background(), ms)
		_, limited := ctx.Deadline()
		if limited != (ms > 0) || ctx.Err() != nil {
			t.Fatalf("incorrect deadline policy %d", ms)
		}
		cancel()
		if ctx.Err() != context.Canceled {
			t.Fatal("no deadline must not disable Cancel")
		}
	}
}
