package contracts

import "fmt"

func validateSetRequirements(field string, wearer Wearer) error {
	if wearer.SelectedSetUID != "" && wearer.SelectedSets != nil {
		return fmt.Errorf("%s has conflicting selected set representations", field)
	}
	sets := wearer.SetRequirements()
	if len(sets) != 1 && len(sets) != 2 {
		return fmt.Errorf("%s requires one 4p or two distinct 2p sets", field)
	}
	for i, set := range sets {
		if err := validateToken(field+".selected_sets.set_uid", set.SetUID); err != nil {
			return err
		}
		expected := 4 / len(sets)
		if set.Count != expected || (i > 0 && sets[i-1].SetUID >= set.SetUID) {
			return fmt.Errorf("%s selected sets must be canonical distinct 4p or 2+2 requirements", field)
		}
	}
	return nil
}
