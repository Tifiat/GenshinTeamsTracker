// Package searchcontrol separates cooperative search completion from cancellation
// of the whole request. Final verification always keeps the outer context.
package searchcontrol

import (
	"context"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

type fileKey struct{}
type controlKey struct{}

type control struct {
	outer     context.Context
	path      string
	cancel    context.CancelFunc
	ready     chan struct{}
	done      chan struct{}
	exited    chan struct{}
	armOnce   sync.Once
	closeOnce sync.Once
	requested atomic.Bool
}

func WithFile(ctx context.Context, path string) context.Context {
	return context.WithValue(ctx, fileKey{}, path)
}

// Begin creates a search-only context. Finish may interrupt preparation; callers
// must report no result explicitly when no complete candidate exists yet.
func Begin(parent context.Context) (context.Context, func()) {
	ctx, cancel := context.WithCancel(parent)
	path, _ := parent.Value(fileKey{}).(string)
	c := &control{outer: parent, path: path, cancel: cancel, ready: make(chan struct{}), done: make(chan struct{}), exited: make(chan struct{})}
	ctx = context.WithValue(ctx, controlKey{}, c)
	c.poll()
	go func() {
		defer close(c.exited)
		ticker := time.NewTicker(25 * time.Millisecond)
		defer ticker.Stop()
		for {
			c.poll()
			select {
			case <-ctx.Done():
				return
			case <-c.done:
				return
			case <-ticker.C:
			}
		}
	}()
	return ctx, func() {
		c.closeOnce.Do(func() { close(c.done); <-c.exited; cancel() })
	}
}

func (c *control) poll() {
	if c.path == "" {
		return
	}
	if info, err := os.Stat(c.path); err == nil && info.Mode().IsRegular() {
		c.requested.Store(true)
		c.cancel()
	}
}

// Ready also checks the marker synchronously at a completed-candidate boundary.
func Ready(ctx context.Context) {
	if c, ok := ctx.Value(controlKey{}).(*control); ok {
		c.armOnce.Do(func() { c.poll(); close(c.ready) })
	}
}

func Requested(ctx context.Context) bool {
	c, ok := ctx.Value(controlKey{}).(*control)
	return ok && c.requested.Load()
}

// Retained results may finish binding/verification after soft Finish, but an
// emergency cancellation of the outer request must still stop all work.
func FinalizationContext(ctx context.Context) context.Context {
	if c, ok := ctx.Value(controlKey{}).(*control); ok {
		return c.outer
	}
	return ctx
}
