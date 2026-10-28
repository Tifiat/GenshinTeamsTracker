package seteffects

// Replay only bounded source callbacks that change effect state. This is NOT a
// second combat simulator. Calls that create attacks, change actions/energy or
// consume RNG remain explicit schedule boundaries. Unknown task phase and the
// character-queue hitlag projection are reported as approximate coverage.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type ruleTask struct {
	frame, owner, serial int
	fn                   any
	vm                   *ruleVM
	choice               RuleChoice
}

func (h *ruleReplayHost) queueTask(owner int, args []any) {
	if len(args) != 2 {
		ruleFail("task callback arity")
	}
	fn, ok := args[0].(*ruleFunction)
	if !ok {
		ruleFail("task callback is not source-backed")
	}
	delay := ruleInteger(args[1])
	if delay < 0 {
		ruleFail("negative task delay requires schedule evidence")
	}
	if owner >= 0 && delay == 0 {
		h.vm.invoke(fn, nil)
		return
	}
	if len(h.tasks) >= 20000 {
		ruleFail("set task queue budget exhausted")
	}
	h.nextTask++
	h.tasks = append(h.tasks, ruleTask{h.frame + delay, owner, h.nextTask, fn, h.vm, h.choice})
	h.uncertainty["counterfactual_task_phase_observed_schedule"] = true
	if owner >= 0 {
		h.uncertainty["character_task_hitlag_projection_approximate"] = true
	}
}

// Strictly earlier frames only: within-frame neutral event/task phase was not
// captured for absent callbacks, so it must not acquire a fake exact order.
func (h *ruleReplayHost) tasksBefore(frame int, world *contracts.NeutralWorldLedger) error {
	for len(h.tasks) > 0 {
		best := -1
		for i, x := range h.tasks {
			if x.frame >= frame {
				continue
			}
			if best < 0 || x.frame < h.tasks[best].frame || (x.frame == h.tasks[best].frame && x.serial < h.tasks[best].serial) {
				best = i
			}
		}
		if best < 0 {
			return nil
		}
		task := h.tasks[best]
		h.tasks = append(h.tasks[:best], h.tasks[best+1:]...)
		h.tasksExecuted++
		if h.tasksExecuted > 20000 {
			return fmt.Errorf("set task execution budget exhausted")
		}
		h.frame, h.vm, h.choice = task.frame, task.vm, task.choice
		h.lifecycle++
		// Retain only preceding observed state. The nearest earlier world's
		// exact order is also the explicit stat-read approximation anchor.
		if world != nil && world.Complete {
			for i := len(world.States) - 1; i >= 0; i-- {
				if world.States[i].Frame < task.frame {
					h.order, h.active = world.States[i].Order, world.States[i].Active
					h.worldAt(world, h.order)
					break
				}
			}
		}
		_, err := ruleTry(func() any { return task.vm.invoke(task.fn, nil) })
		if err != nil {
			return fmt.Errorf("%s task: %w", task.choice.Key, err)
		}
	}
	return nil
}
