package main

import (
	"context"
	"time"
)

// Zero is the production no-deadline policy. Explicit positive deadlines remain
// available to bounded diagnostic harnesses; they are never silently renewed.
func productContext(ctx context.Context, timeoutMS int64) (context.Context, context.CancelFunc) {
	if timeoutMS > 0 {
		return context.WithTimeout(ctx, time.Duration(timeoutMS)*time.Millisecond)
	}
	return context.WithCancel(ctx)
}
