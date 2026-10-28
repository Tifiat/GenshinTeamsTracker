package theorysearch

import (
	"context"
	"errors"
	"fmt"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

var ErrNoResult = errors.New("finish_no_result: no complete legal Theory witness")
var ErrBindingChanged = errors.New("Theory input/model/engine binding changed")

// A session owns two independent live branches after first publication. The
// archive is output-only: optional breadth discoveries never feed common-H.
type Session struct {
	cfg     Config
	active  *branch
	preDeep *branch
	archive *branch
	phase   string
	version int64
	failure error
	closed  bool
}

func New(cfg Config, w Resolver) (*Session, error) {
	if w == nil || cfg.Binding == "" || cfg.RequestSHA256 == "" || cfg.SessionID == "" {
		return nil, fmt.Errorf("missing Theory session identity")
	}
	if err := alloc.ValidateFull45(cfg.Initial); err != nil {
		return nil, err
	}
	owners := map[string]bool{}
	for a, rows := range cfg.Domains {
		if cfg.Wearers[a] == "" || owners[cfg.Wearers[a]] || len(rows) == 0 {
			return nil, fmt.Errorf("invalid Theory wearer/domain")
		}
		owners[cfg.Wearers[a]] = true
		keys := map[string]bool{}
		cfg.Domains[a] = make([]domain.Package, len(rows))
		for i, p := range rows {
			if err := p.Validate(); err != nil {
				return nil, err
			}
			if keys[p.Key()] {
				return nil, fmt.Errorf("duplicate Theory package domain")
			}
			keys[p.Key()] = true
			cfg.Domains[a][i] = copyPackages([4]domain.Package{p})[0]
		}
		if !keys[cfg.Original[a].Key()] {
			return nil, fmt.Errorf("Theory original tuple outside allowed domain")
		}
	}
	cfg.Original = copyPackages(cfg.Original)
	return &Session{cfg: cfg, active: newBranch(w, cfg.Initial), archive: newBranch(nil, cfg.Initial)}, nil
}
func (s *Session) check(binding string, phase ...string) error {
	if binding != s.cfg.Binding {
		s.abort(ErrBindingChanged)
		return ErrBindingChanged
	}
	if s.closed {
		return fmt.Errorf("Theory session is closed")
	}
	for _, p := range phase {
		if s.phase == p {
			return nil
		}
	}
	return fmt.Errorf("Theory action unavailable in phase %q", s.phase)
}
func (s *Session) absorb() {
	if s.active == nil {
		return
	}
	// Keep all legal lower witnesses and exact aliases found on either branch.
	for f, c := range s.active.pool {
		if old, ok := s.archive.pool[f]; !ok || c.value > old.value {
			s.archive.pool[f] = copyCandidate(c)
		}
		if s.active.refined[f] > s.archive.refined[f] {
			s.archive.refined[f] = s.active.refined[f]
		}
	}
	for f, rows := range s.active.aliases {
		if s.archive.aliases[f] == nil {
			s.archive.aliases[f] = map[string]Alias{}
		}
		for k, v := range rows {
			s.archive.aliases[f][k] = cloneAlias(v)
		}
	}
	for k, v := range s.active.unavailable {
		s.archive.unavailable[k] = cloneUnavailable(v)
	}
	for k, v := range s.active.visited {
		s.archive.visited[k] = v
	}
}
func (s *Session) abort(err error) {
	s.absorb()
	s.failure = err
	s.Close()
}
func (s *Session) First(ctx context.Context, binding string) (Snapshot, error) {
	if err := s.check(binding, ""); err != nil {
		return Snapshot{}, err
	}
	if err := s.active.start(ctx, s.cfg); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	if err := s.active.pass(ctx, s.cfg, 0); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	s.absorb()
	checkpoint, err := s.active.fork()
	if err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	s.preDeep = checkpoint
	s.phase = "first_light"
	return s.publish(false), nil
}
func (s *Session) Breadth(ctx context.Context, binding string) (Snapshot, error) {
	if err := s.check(binding, "first_light"); err != nil {
		return Snapshot{}, err
	}
	if err := s.active.pass(ctx, s.cfg, 1); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	s.absorb()
	s.phase = "breadth_light"
	return s.publish(false), nil
}
func (s *Session) Deep(ctx context.Context, binding string) (Snapshot, error) {
	if err := s.check(binding, "first_light", "breadth_light"); err != nil {
		return Snapshot{}, err
	}
	// Restore the full pre-deep state, including mutable resolver caches and
	// numerical feedback. Do not restart/repeat the first catalog pass.
	s.absorb()
	s.active.close()
	s.active = s.preDeep
	s.preDeep = nil
	if err := s.active.deep(ctx, s.cfg); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	if err := s.active.pass(ctx, s.cfg, 1); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	if err := s.active.deep(ctx, s.cfg); err != nil {
		s.abort(err)
		return Snapshot{}, err
	}
	s.absorb()
	s.phase = "deep_baseline"
	return s.publish(false), nil
}
func (s *Session) Finish() (Snapshot, error) {
	s.absorb()
	if s.failure != nil && !errors.Is(s.failure, context.Canceled) {
		return Snapshot{}, s.failure
	}
	if len(s.archive.pool) == 0 {
		s.Close()
		return Snapshot{}, ErrNoResult
	}
	out := s.publish(true)
	s.Close()
	return out, nil
}
func (s *Session) Close() {
	if s == nil || s.closed {
		return
	}
	s.active.close()
	s.preDeep.close()
	s.closed = true
}
