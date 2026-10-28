package contracts

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestDecodedCanonicalEncodingMatchesExistingRoundTrip(t *testing.T) {
	for _, raw := range []string{
		`{"b":1e3,"a":[null,false,0,-0,1.50,18446744073709551615]}`,
		`{"text":"<>&\u2028\u2029", "nested":{"z":[],"a":{}},"unicode":"тест"}`,
		`[{},[],null,true,"x"]`,
	} {
		decoder := json.NewDecoder(bytes.NewBufferString(raw))
		decoder.UseNumber()
		var generic any
		if err := decoder.Decode(&generic); err != nil {
			t.Fatal(err)
		}
		old, err := CanonicalJSON(generic)
		if err != nil {
			t.Fatal(err)
		}
		direct, err := canonicalizeRawJSON([]byte(raw))
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(old, direct) {
			t.Fatalf("canonical identity drift: %s != %s", old, direct)
		}
	}
}
