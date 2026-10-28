package engineclient

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"
)

func TestR5StreamingIntegrityRetainsEveryCheck(t *testing.T) {
	path := filepath.Join(t.TempDir(), "owned.bin")
	data := make([]byte, 3*1024*1024+17)
	for i := range data {
		data[i] = byte(i * 13)
	}
	hash := sha256.Sum256(data)
	expected := hex.EncodeToString(hash[:])
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	if err := verifyFileSHA256(path, expected); err != nil {
		t.Fatal(err)
	}
	data[len(data)/2] ^= 1
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	if err := verifyFileSHA256(path, expected); err == nil {
		t.Fatal("mutated binary accepted")
	}
	if err := os.Truncate(path, 0); err != nil {
		t.Fatal(err)
	}
	if err := verifyFileSHA256(path, expected); err == nil {
		t.Fatal("truncation accepted")
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := verifyFileSHA256(path, expected); err == nil {
		t.Fatal("missing binary accepted")
	}
}
