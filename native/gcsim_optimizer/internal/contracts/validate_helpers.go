package contracts

import (
	"fmt"
	"math/big"
	"regexp"
	"strings"
)

var (
	sha256Pattern  = regexp.MustCompile(`^[0-9a-f]{64}$`)
	tokenPattern   = regexp.MustCompile(`^[a-z0-9][a-z0-9_.:/-]*$`)
	decimalPattern = regexp.MustCompile(`^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$`)
)

var canonicalSlots = []string{"flower", "plume", "sands", "goblet", "circlet"}

func validateHeader(version int, got, expected string) error {
	if version != SchemaVersion {
		return fmt.Errorf("unsupported schema_version %d; expected %d", version, SchemaVersion)
	}
	if got != expected {
		return fmt.Errorf("unsupported schema_kind %q; expected %q", got, expected)
	}
	return nil
}

func validateSHA256(field, value string, optional bool) error {
	if optional && value == "" {
		return nil
	}
	if !sha256Pattern.MatchString(value) {
		return fmt.Errorf("%s must be a lowercase SHA-256 digest", field)
	}
	return nil
}

func validateToken(field, value string) error {
	if !tokenPattern.MatchString(value) {
		return fmt.Errorf("%s must be a non-empty stable lowercase token", field)
	}
	return nil
}

func validateDecimal(field, value string) error {
	if !decimalPattern.MatchString(value) || value == "-0" {
		return fmt.Errorf("%s must be canonical decimal text", field)
	}
	if _, ok := new(big.Rat).SetString(value); !ok {
		return fmt.Errorf("%s is not a finite decimal", field)
	}
	return nil
}

func validateUnitDecimal(field, value string) error {
	if err := validateDecimal(field, value); err != nil {
		return err
	}
	ratio, _ := new(big.Rat).SetString(value)
	if ratio.Sign() < 0 || ratio.Cmp(big.NewRat(1, 1)) > 0 {
		return fmt.Errorf("%s must be between 0 and 1", field)
	}
	return nil
}

func validateNonNegativeDecimal(field, value string) error {
	if err := validateDecimal(field, value); err != nil {
		return err
	}
	ratio, _ := new(big.Rat).SetString(value)
	if ratio.Sign() < 0 {
		return fmt.Errorf("%s must not be negative", field)
	}
	return nil
}

func validateSortedUniqueStrings(field string, values []string) error {
	for index, value := range values {
		if err := validateToken(fmt.Sprintf("%s[%d]", field, index), value); err != nil {
			return err
		}
		if index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be strictly sorted and unique", field)
		}
	}
	return nil
}

func validateSortedUniqueInt64(field string, values []int64) error {
	for index, value := range values {
		if value <= 0 {
			return fmt.Errorf("%s[%d] must be positive", field, index)
		}
		if index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be strictly sorted and unique", field)
		}
	}
	return nil
}

func validateSortedUniqueUint64(field string, values []uint64) error {
	for index, value := range values {
		if index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be strictly sorted and unique", field)
		}
	}
	return nil
}

func slotIndex(slot string) int {
	for index, candidate := range canonicalSlots {
		if candidate == slot {
			return index
		}
	}
	return -1
}

func validSlot(slot string) bool {
	for _, candidate := range canonicalSlots {
		if candidate == slot {
			return true
		}
	}
	return false
}

func compareAssignments(left, right ArtifactAssignment) int {
	if comparison := strings.Compare(left.WearerKey, right.WearerKey); comparison != 0 {
		return comparison
	}
	leftSlot := slotIndex(left.Slot)
	rightSlot := slotIndex(right.Slot)
	if leftSlot < rightSlot {
		return -1
	}
	if leftSlot > rightSlot {
		return 1
	}
	return 0
}
