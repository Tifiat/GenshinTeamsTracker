package contracts

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
)

// CanonicalJSON emits UTF-8 JSON with sorted object keys, no insignificant
// whitespace, and Go-compatible U+2028/U+2029 escaping. Contract decimals are
// strings, so cross-language floating-point formatting cannot change identity.
func CanonicalJSON(value any) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("marshal contract: %w", err)
	}

	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var generic any
	if err := decoder.Decode(&generic); err != nil {
		return nil, fmt.Errorf("decode contract for canonicalization: %w", err)
	}

	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(generic); err != nil {
		return nil, fmt.Errorf("encode canonical contract: %w", err)
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}

func CanonicalSHA256(value any) (string, error) {
	encoded, err := CanonicalJSON(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func TextSHA256(text string) string {
	digest := sha256.Sum256([]byte(text))
	return hex.EncodeToString(digest[:])
}

func decodeStrict[T any](data []byte) (T, error) {
	var value T
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&value); err != nil {
		return value, fmt.Errorf("decode contract: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return value, fmt.Errorf("decode contract: multiple JSON values")
		}
		return value, fmt.Errorf("decode contract trailing data: %w", err)
	}
	inputCanonical, err := canonicalizeRawJSON(data)
	if err != nil {
		return value, err
	}
	typedCanonical, err := CanonicalJSON(value)
	if err != nil {
		return value, err
	}
	if !bytes.Equal(inputCanonical, typedCanonical) {
		return value, fmt.Errorf("decode contract: missing, null, or non-canonical fields")
	}
	return value, nil
}

func canonicalizeRawJSON(data []byte) ([]byte, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var generic any
	if err := decoder.Decode(&generic); err != nil {
		return nil, fmt.Errorf("decode raw contract for canonical comparison: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, fmt.Errorf("decode raw contract trailing data: %w", err)
	}
	return CanonicalJSON(generic)
}

func DecodeRequest(data []byte) (OptimizerRequest, error) {
	value, err := decodeStrict[OptimizerRequest](data)
	if err != nil {
		return value, err
	}
	return value, value.Validate()
}

func DecodeCompactIR(data []byte) (CompactIR, error) {
	value, err := decodeStrict[CompactIR](data)
	if err != nil {
		return value, err
	}
	return value, value.Validate()
}

// DecodeSeedMember validates the direct compact payload emitted by one
// isolated engine execution before it is wrapped in request/context identities.
func DecodeSeedMember(data []byte) (IRSeedMember, error) {
	value, err := decodeStrict[IRSeedMember](data)
	if err != nil {
		return value, err
	}
	return value, ValidateSeedMember(value)
}

func DecodeProgress(data []byte) (ProgressRecord, error) {
	value, err := decodeStrict[ProgressRecord](data)
	if err != nil {
		return value, err
	}
	return value, value.Validate()
}

func DecodeResult(data []byte) (OptimizerResult, error) {
	value, err := decodeStrict[OptimizerResult](data)
	if err != nil {
		return value, err
	}
	return value, value.Validate()
}
