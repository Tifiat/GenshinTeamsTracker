package contracts

// Inert synthetic overlay tests. No saved inputs, benchmark, engine or opt-in job.
import (
	"bytes"
	"crypto/sha256"
	"encoding"
	"encoding/json"
	"fmt"
	"io"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func seedCanonicalFixture(ledger bool) IRSeedMember {
	m := IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("a", 64),
		Nodes: []IRNode{{NodeID: 1, Operation: "constant", Inputs: []IRInput{}, Value: "1"}},
		Channels: []IRChannel{{ChannelID: "hit", Kind: "direct", ActorKey: "actor", AttackTag: "normal", DamageType: "physical", RootNodeID: 1, HitCount: 1, BaselineDamage: "1", ResponseCoordinates: []string{}}},
		OpaqueBoundaries: []IROpaqueBoundary{}}
	if ledger {
		m.EnergyLedger = &IREnergyLedger{InitialStates: []IREnergyCharacterState{{CharacterIndex: 0, CharacterKey: "actor", Energy: "0", EnergyMax: "60"}}, Events: []IREnergyEvent{}, UncertaintyCodes: []string{}}
	}
	return m
}

func seedCanonicalCheck(t *testing.T, member IRSeedMember) {
	t.Helper()
	before, err := json.Marshal(member)
	if err != nil { t.Fatal("fixture snapshot failed") }
	old, oldErr := CanonicalJSON(member)
	view, viewErr := encodeCanonicalJSON(seedMemberCanonicalView(member))
	fast, fastErr := canonicalDecodedContract(member)
	if oldErr != nil || viewErr != nil || fastErr != nil || !bytes.Equal(old, view) || !bytes.Equal(old, fast) || sha256.Sum256(old) != sha256.Sum256(fast) {
		t.Fatal("canonical bytes or digest differ")
	}
	after, err := json.Marshal(member)
	if err != nil || !bytes.Equal(before, after) { t.Fatal("canonical conversion mutated input") }
}

func TestSeedMemberTypedCanonicalBytes(t *testing.T) {
	// All fast-path strings have passed Decoder; invalid UTF-8 is normalized first.
	fixtures := []IRSeedMember{{}, {Nodes: []IRNode{}, Channels: []IRChannel{}, OpaqueBoundaries: []IROpaqueBoundary{}}, seedCanonicalFixture(false), seedCanonicalFixture(true)}
	maxInt := int(^uint(0) >> 1)
	texts := []string{"", "0", "-0", "1.000", "-12345678901234567890.0123456789", "1e+09", "<>&\"\\\n\t", "\u2028\u2029", "\ufffd", "\x00", "日本語"}
	for i := 0; i < 128; i++ {
		text := texts[i%len(texts)]
		member := IRSeedMember{Seed: ^uint64(0), DurationMS: -1 << 63, TopologySHA256: text,
			Nodes: []IRNode{{NodeID: ^uint32(0), Operation: text, Value: text, Coordinate: text, Inputs: []IRInput{{NodeID: ^uint32(0), Relation: text}}}},
			Channels: []IRChannel{{ChannelID: text, Kind: text, ActorKey: text, AttackTag: text, DamageType: text, RootNodeID: ^uint32(0), HitCount: maxInt, BaselineDamage: text, ResponseCoordinates: []string{text}}},
			OpaqueBoundaries: []IROpaqueBoundary{{BoundaryID: text, NodeID: ^uint32(0), ReasonCode: text, BaselineDamage: text, BaselineDamageShare: text}},
			EnergyLedger: &IREnergyLedger{InitialStates: []IREnergyCharacterState{{CharacterIndex: maxInt, CharacterKey: text, Energy: text, EnergyMax: text}},
				Events: []IREnergyEvent{{SequenceIndex: maxInt, Frame: -maxInt-1, CharacterIndex: maxInt, CharacterKey: text, Kind: text, Source: text, EnergyBefore: text, EnergyAfter: text, EnergyMax: text, Amount: text}}, UncertaintyCodes: []string{text}}}
		if i%2 == 0 { member.Seed = 0; member.DurationMS = 1<<63-1; member.Channels[0].HitCount = -maxInt-1 }
		if i%5 == 0 {
			member.Nodes[0].NodeID = 0; member.Nodes[0].Inputs[0].NodeID = 0; member.Channels[0].RootNodeID = 0; member.OpaqueBoundaries[0].NodeID = 0
			member.EnergyLedger.InitialStates[0].CharacterIndex = -maxInt-1
			member.EnergyLedger.Events[0].SequenceIndex = -maxInt-1; member.EnergyLedger.Events[0].Frame = maxInt; member.EnergyLedger.Events[0].CharacterIndex = -maxInt-1
		}
		if i%3 == 0 { member.Nodes[0].Inputs = nil; member.Channels[0].ResponseCoordinates = nil }
		if i%4 == 0 { member.EnergyLedger.Events = nil; member.EnergyLedger.InitialStates = nil; member.EnergyLedger.UncertaintyCodes = nil }
		if i%4 == 1 { member.EnergyLedger.Events = []IREnergyEvent{}; member.EnergyLedger.InitialStates = []IREnergyCharacterState{}; member.EnergyLedger.UncertaintyCodes = []string{} }
		if len(member.EnergyLedger.Events) > 0 {
			flag := i%2 == 0
			if i%3 != 0 { member.EnergyLedger.Events[0].RawAtER100 = &text; member.EnergyLedger.Events[0].ObservedER = &text; member.EnergyLedger.Events[0].OnField = &flag }
		}
		fixtures = append(fixtures, member)
	}
	var normalized IRSeedMember
	if json.Unmarshal([]byte("{\"topology_sha256\":\"\xff\"}"), &normalized) != nil { t.Fatal("UTF-8 normalization fixture failed") }
	fixtures = append(fixtures, normalized)
	for _, member := range fixtures { seedCanonicalCheck(t, member) }
}

func TestSeedMemberTypedCanonicalSchema(t *testing.T) {
	pairs := [][2]reflect.Type{
		{reflect.TypeOf(IRSeedMember{}), reflect.TypeOf(canonicalSeedMember{})},
		{reflect.TypeOf(IRNode{}), reflect.TypeOf(canonicalIRNode{})},
		{reflect.TypeOf(IRChannel{}), reflect.TypeOf(canonicalIRChannel{})},
		{reflect.TypeOf(IROpaqueBoundary{}), reflect.TypeOf(canonicalIROpaqueBoundary{})},
		{reflect.TypeOf(IREnergyLedger{}), reflect.TypeOf(canonicalIREnergyLedger{})},
		{reflect.TypeOf(IREnergyEvent{}), reflect.TypeOf(canonicalIREnergyEvent{})},
	}
	replacements := map[reflect.Type]reflect.Type{}
	for _, pair := range pairs { replacements[pair[0]] = pair[1] }
	var shape func(reflect.Type, reflect.Type) bool
	shape = func(a, b reflect.Type) bool {
		if replacement, ok := replacements[a]; ok { return b == replacement }
		if a.Kind() == reflect.Slice || a.Kind() == reflect.Pointer { return a.Kind() == b.Kind() && shape(a.Elem(), b.Elem()) }
		return a == b
	}
	marshalJSON := reflect.TypeOf((*json.Marshaler)(nil)).Elem()
	marshalText := reflect.TypeOf((*encoding.TextMarshaler)(nil)).Elem()
	checkMethods := func(typ reflect.Type) {
		if typ.Implements(marshalJSON) || reflect.PointerTo(typ).Implements(marshalJSON) || typ.Implements(marshalText) || reflect.PointerTo(typ).Implements(marshalText) { t.Fatal("schema gained custom marshaling") }
	}
	checkSorted := func(typ reflect.Type) {
		keys := []string{}
		for i := 0; i < typ.NumField(); i++ { keys = append(keys, strings.Split(typ.Field(i).Tag.Get("json"), ",")[0]) }
		if !sort.StringsAreSorted(keys) { t.Fatal("canonical field order differs") }
	}
	for _, pair := range pairs {
		old, mirror := pair[0], pair[1]
		checkMethods(old); checkMethods(mirror); checkSorted(mirror)
		if old.NumField() != mirror.NumField() { t.Fatal("schema field count differs") }
		for i := 0; i < old.NumField(); i++ {
			field := old.Field(i)
			other, ok := mirror.FieldByName(field.Name)
			if !ok || field.Tag != other.Tag || field.Anonymous != other.Anonymous || field.PkgPath != other.PkgPath || !shape(field.Type, other.Type) { t.Fatal("schema field tag or shape differs") }
		}
	}
	for _, typ := range []reflect.Type{reflect.TypeOf(IRInput{}), reflect.TypeOf(IREnergyCharacterState{})} { checkMethods(typ); checkSorted(typ) }
}

// Frozen canonical.go decodeStrict body: only this function name is changed.
func seedCanonicalFrozenDecodeStrict[T any](data []byte) (T, error) {
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

func TestSeedMemberTypedCanonicalStrictDecode(t *testing.T) {
	base, err := CanonicalJSON(seedCanonicalFixture(false))
	if err != nil { t.Fatal("strict fixture encoding failed") }
	ledger, err := CanonicalJSON(seedCanonicalFixture(true))
	if err != nil { t.Fatal("ledger fixture encoding failed") }
	for _, raw := range [][]byte{base, ledger} {
		if _, err := DecodeSeedMember(raw); err != nil { t.Fatal("valid strict fixture rejected") }
	}
	// Structurally invalid graphs use strict-decode comparison without semantic validation.
	cases := [][]byte{base, ledger, []byte("{}"), []byte("null"), []byte("[]"), []byte(""), []byte("{"),
		append(append([]byte{}, base...), []byte(" {}")...), append(append([]byte{}, base...), 'x'),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":1,"seed":2`, 1)),
		[]byte(strings.Replace(string(ledger), `"energy_ledger":{`, `"energy_ledger":{},"energy_ledger":{`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":1.0`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":1e0`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":-1`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":18446744073709551616`, 1)),
		[]byte(strings.Replace(string(base), `"duration_ms":1000`, `"duration_ms":9223372036854775808`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":null`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1,`, ``, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":1,"unknown":0`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"\u0073eed":1`, 1)),
		[]byte(strings.Replace(string(base), `"opaque_boundaries":[]`, `"opaque_boundaries":null`, 1)),
		[]byte(strings.Replace(string(base), `"seed":1`, `"seed":1,"energy_ledger":null`, 1)),
		[]byte(strings.Replace(string(base), `"value":"1"`, `"value":""`, 1)),
		[]byte(strings.Replace(string(base), `"value":"1"`, `"value":null`, 1)),
	}
	for _, text := range []string{`\ud800`, `\udfff`, `\ud83d\ude00`, `\u2028\u2029`, "\xff", `<>&`} {
		cases = append(cases, []byte(strings.Replace(string(base), `"value":"1"`, `"value":"`+text+`"`, 1)))
	}
	optional := seedCanonicalFixture(true)
	empty, flag := "", false
	optional.EnergyLedger.Events = []IREnergyEvent{{RawAtER100: &empty, ObservedER: &empty, OnField: &flag}}
	optionalRaw, err := CanonicalJSON(optional)
	if err != nil { t.Fatal("optional strict fixture encoding failed") }
	cases = append(cases, optionalRaw)
	for _, replacement := range [][2]string{
		{`"on_field":false`, `"on_field":null`}, {`"on_field":false,`, ``},
		{`"raw_at_er_100":""`, `"raw_at_er_100":null`}, {`"raw_at_er_100":"",`, ``},
		{`"observed_er":""`, `"observed_er":null`}, {`"observed_er":"",`, ``},
		{`"events":[`, `"events":null,"events":[`},
		{`"character_index":0`, `"character_index":1.0`},
	} { cases = append(cases, []byte(strings.Replace(string(optionalRaw), replacement[0], replacement[1], 1))) }
	for _, raw := range cases {
		before := append([]byte(nil), raw...)
		old, oldErr := seedCanonicalFrozenDecodeStrict[IRSeedMember](raw)
		candidate, candidateErr := decodeStrict[IRSeedMember](raw)
		if !reflect.DeepEqual(old, candidate) || (oldErr == nil) != (candidateErr == nil) || fmt.Sprint(oldErr) != fmt.Sprint(candidateErr) { t.Fatal("strict decoded value or error differs") }
		if !bytes.Equal(before, raw) { t.Fatal("strict decode mutated input") }
	}
	// Full API parity uses only valid or single-error fixtures, avoiding map-order errors.
	for _, raw := range [][]byte{base, ledger, []byte("{}"), []byte("null"), append(append([]byte{}, base...), 'x')} {
		old, oldErr := seedCanonicalFrozenDecodeStrict[IRSeedMember](raw)
		if oldErr == nil { oldErr = ValidateSeedMember(old) }
		candidate, candidateErr := DecodeSeedMember(raw)
		if !reflect.DeepEqual(old, candidate) || (oldErr == nil) != (candidateErr == nil) || fmt.Sprint(oldErr) != fmt.Sprint(candidateErr) { t.Fatal("seed member API parity differs") }
	}
}

func TestSeedMemberTypedCanonicalScope(t *testing.T) {
	member := seedCanonicalFixture(false)
	invalidMember := member
	invalidMember.TopologySHA256 = "\xff"
	values := []any{nil, true, "<>&\u2028\u2029", json.Number("1.00"), []int{}, map[string]any{"z": "<>", "a": 1}, IRInput{}, IREnergyCharacterState{}, &member, CompactIR{}, "\xff", &invalidMember, make(chan int)}
	for _, value := range values {
		old, oldErr := CanonicalJSON(value)
		candidate, candidateErr := canonicalDecodedContract(value)
		if !bytes.Equal(old, candidate) || (oldErr == nil) != (candidateErr == nil) || fmt.Sprint(oldErr) != fmt.Sprint(candidateErr) { t.Fatal("fallback canonical behavior differs") }
	}
	// Public CanonicalJSON must retain its marshal/decode normalization semantics.
	member.TopologySHA256 = "\xff<&\u2028\u2029"
	before, err := json.Marshal(member)
	if err != nil { t.Fatal("public canonical fixture failed") }
	var normalized IRSeedMember
	if json.Unmarshal(before, &normalized) != nil { t.Fatal("public normalization failed") }
	public, publicErr := CanonicalJSON(member)
	want, wantErr := CanonicalJSON(normalized)
	if publicErr != nil || wantErr != nil || !bytes.Equal(public, want) || !bytes.Contains(public, []byte("\ufffd")) { t.Fatal("public invalid UTF-8 semantics changed") }
	after, err := json.Marshal(member)
	if err != nil || !bytes.Equal(before, after) { t.Fatal("public canonical mutated input") }
}
