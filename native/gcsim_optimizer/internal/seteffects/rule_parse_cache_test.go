package seteffects

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"go/ast"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestRuleParseCacheColdWarmNameAndSourceKeys(t *testing.T) {
	dir := t.TempDir()
	name := "pkg/rule.go"
	source := []byte("package sample\nfunc Start() int { return 42 }\n")
	cache := NewRuleParseCache("", dir)
	first, err := cache.loadFile(name, source)
	if err != nil {
		t.Fatal(err)
	}
	second, err := cache.loadFile(name, source)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatal("memory cache did not share the immutable parsed AST")
	}
	stats := cache.Stats()
	if stats.Misses != 1 || stats.Writes != 1 || stats.Hits != 1 || stats.MemoryHits != 1 {
		t.Fatalf("unexpected cold and memory hit stats: %+v", stats)
	}

	warm := NewRuleParseCache("", dir)
	if _, err := warm.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	if got := warm.Stats(); got.WritableHits != 1 || got.Misses != 0 || got.Writes != 0 {
		t.Fatalf("unexpected disk warm stats: %+v", got)
	}
	if _, err := warm.loadFile("pkg/other.go", source); err != nil {
		t.Fatal(err)
	}
	changed := []byte("package sample\nfunc Start() int { return 43 }\n")
	if _, err := warm.loadFile(name, changed); err != nil {
		t.Fatal(err)
	}
	if cache.sourceKey(name, source) == cache.sourceKey("pkg/other.go", source) || cache.sourceKey(name, source) == cache.sourceKey(name, changed) {
		t.Fatal("source cache key ignored the file name or source bytes")
	}
	if got := warm.Stats(); got.WritableHits != 1 || got.Misses != 2 || got.Writes != 2 {
		t.Fatalf("different names and bytes were not independently parsed: %+v", got)
	}
}

func TestRuleParseCacheRepairsCorruptAndOldSchemaFiles(t *testing.T) {
	for _, corrupt := range []string{"payload", "schema"} {
		t.Run(corrupt, func(t *testing.T) {
			dir := t.TempDir()
			name := "pkg/repair.go"
			source := []byte("package sample\nfunc Start() int { return 7 }\n")
			cache := NewRuleParseCache("", dir)
			key := cache.sourceKey(name, source)
			path := filepath.Join(dir, key+ruleParseCacheExtension)
			if err := os.MkdirAll(dir, 0o700); err != nil {
				t.Fatal(err)
			}
			var original []byte
			if corrupt == "payload" {
				original = []byte("not an AST cache")
			} else {
				parsed, err := parseRuleAST(name, source)
				if err != nil {
					t.Fatal(err)
				}
				original, err = encodeRuleParseCacheFile(name, source, parsed, ruleParseCacheSchema-1, runtime.Version())
				if err != nil {
					t.Fatal(err)
				}
			}
			if err := os.WriteFile(path, original, 0o600); err != nil {
				t.Fatal(err)
			}
			if _, err := cache.loadFile(name, source); err != nil {
				t.Fatal(err)
			}
			if got := cache.Stats(); got.Misses != 1 || got.Repairs != 1 || got.Writes != 1 || got.Errors == 0 {
				t.Fatalf("cache was not repaired: %+v", got)
			}
			warm := NewRuleParseCache("", dir)
			if _, err := warm.loadFile(name, source); err != nil {
				t.Fatal(err)
			}
			if got := warm.Stats(); got.WritableHits != 1 || got.Misses != 0 {
				t.Fatalf("repaired entry was not usable: %+v", got)
			}
		})
	}
}

func TestRuleParseCacheRepairsHeaderIdentityMismatch(t *testing.T) {
	for _, field := range []string{"name", "source", "go version"} {
		t.Run(field, func(t *testing.T) {
			dir := t.TempDir()
			name := "pkg/header.go"
			source := []byte("package sample\nfunc Start() int { return 5 }\n")
			cache := NewRuleParseCache("", dir)
			file, err := parseRuleAST(name, source)
			if err != nil {
				t.Fatal(err)
			}
			data, err := encodeRuleParseCacheFile(name, source, file, ruleParseCacheSchema, runtime.Version())
			if err != nil {
				t.Fatal(err)
			}
			data = rewriteRuleParseCacheHeader(t, data, func(header *ruleParseCacheHeader) {
				switch field {
				case "name":
					header.Name = "pkg/another.go"
				case "source":
					header.SourceSHA256 = sha256Hex([]byte("different source"))
				case "go version":
					header.GoVersion = "go0.0.0-test"
				}
			})
			path := filepath.Join(dir, cache.sourceKey(name, source)+ruleParseCacheExtension)
			if err := os.WriteFile(path, data, 0o600); err != nil {
				t.Fatal(err)
			}
			if _, err := cache.loadFile(name, source); err != nil {
				t.Fatal(err)
			}
			if got := cache.Stats(); got.Repairs != 1 || got.Misses != 1 || got.Writes != 1 {
				t.Fatalf("mismatched header was not repaired: %+v", got)
			}
		})
	}
}

func rewriteRuleParseCacheHeader(t *testing.T, data []byte, mutate func(*ruleParseCacheHeader)) []byte {
	t.Helper()
	prefix := len(ruleParseCacheMagic) + 4 + 8
	if len(data) < prefix || string(data[:len(ruleParseCacheMagic)]) != ruleParseCacheMagic {
		t.Fatal("test fixture is not a rule AST cache file")
	}
	headerStart := prefix
	headerSize := binary.BigEndian.Uint32(data[len(ruleParseCacheMagic) : len(ruleParseCacheMagic)+4])
	payloadStart := headerStart + int(headerSize)
	if payloadStart > len(data) {
		t.Fatal("test fixture has an invalid header size")
	}
	var header ruleParseCacheHeader
	if err := json.Unmarshal(data[headerStart:payloadStart], &header); err != nil {
		t.Fatal(err)
	}
	mutate(&header)
	headerBytes, err := json.Marshal(header)
	if err != nil {
		t.Fatal(err)
	}
	payload := data[payloadStart:]
	rewritten := make([]byte, prefix+len(headerBytes)+len(payload))
	copy(rewritten, ruleParseCacheMagic)
	binary.BigEndian.PutUint32(rewritten[len(ruleParseCacheMagic):], uint32(len(headerBytes)))
	binary.BigEndian.PutUint64(rewritten[len(ruleParseCacheMagic)+4:], uint64(len(payload)))
	copy(rewritten[prefix:], headerBytes)
	copy(rewritten[prefix+len(headerBytes):], payload)
	return rewritten
}

func TestRuleParseCacheReadOnlyAndMemoryOnlyModes(t *testing.T) {
	name := "pkg/readonly.go"
	source := []byte("package sample\nfunc Start() int { return 9 }\n")
	readOnlyDir := t.TempDir()
	writer := NewRuleParseCache("", readOnlyDir)
	if _, err := writer.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	readOnly := NewRuleParseCache(readOnlyDir, "")
	if _, err := readOnly.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	if got := readOnly.Stats(); got.BundledHits != 1 || got.Writes != 0 || got.Misses != 0 {
		t.Fatalf("read-only bundled cache was not used: %+v", got)
	}

	memory := NewRuleParseCache("", "")
	first, err := memory.loadFile(name, source)
	if err != nil {
		t.Fatal(err)
	}
	second, err := memory.loadFile(name, source)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatal("memory-only cache did not share its parsed AST")
	}
	if got := memory.Stats(); got.Misses != 1 || got.Writes != 0 || got.MemoryHits != 1 {
		t.Fatalf("unexpected memory-only stats: %+v", got)
	}
}

func TestRuleParseCacheDoesNotRememberParseErrors(t *testing.T) {
	cache := NewRuleParseCache("", "")
	for range 2 {
		if _, err := cache.loadFile("bad.go", []byte("package sample\nfunc {")); err == nil {
			t.Fatal("invalid syntax unexpectedly parsed")
		}
	}
	if got := cache.Stats(); got.Misses != 2 || got.Errors != 2 || got.Hits != 0 {
		t.Fatalf("parse failure was cached: %+v", got)
	}
}

func TestRuleParseCacheSyntaxCodecRoundTripsAST(t *testing.T) {
	name := "pkg/roundtrip.go"
	source := []byte(`package sample
import output "fmt"
type Pair struct { Left, Right int }
func Start(items []int) int {
	var pair Pair
	defer output.Print(pair.Left)
	sum := 0
	for index, value := range items {
		if value > 0 { sum += value } else if index > 0 { continue }
	}
	switch sum { case 0: return 0; default: return sum }
}`)
	parsed, err := parseRuleAST(name, source)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := encodeRuleParseCacheFile(name, source, parsed, ruleParseCacheSchema, runtime.Version())
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := decodeRuleParseCacheFile(name, source, encoded)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(parsed, decoded) {
		t.Fatal("syntax cache round-trip changed the parsed AST")
	}
}

func TestRuleParseCacheSyntaxCodecRejectsMalformedLengthsAndTags(t *testing.T) {
	filePrefix := []byte{0, 1, 1, 1, 6, 's', 'a', 'm', 'p', 'l', 'e', 0}
	oversizedDecls := append(append([]byte(nil), filePrefix...), 1)
	oversizedDecls = appendRuleASTTestUvarint(oversizedDecls, maxASTNodes+1)
	invalidTag := append(append([]byte(nil), filePrefix...), 1, 1, 0xff)
	oversizedName := append(append([]byte(nil), filePrefix[:3]...), 1)
	oversizedName = appendRuleASTTestUvarint(oversizedName, ruleParseCacheMaxPayload+1)
	trailing := append(append([]byte(nil), filePrefix...), 0, 0, 0, 0, 0, 0, 0, 0, 0xff)
	tests := []struct {
		name    string
		payload []byte
		want    string
	}{
		{name: "oversized declaration slice", payload: oversizedDecls, want: "length"},
		{name: "invalid node tag", payload: invalidTag, want: "tag"},
		{name: "oversized package identifier", payload: oversizedName, want: "length"},
		{name: "trailing byte", payload: trailing, want: "trailing"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if _, err := decodeRuleASTPayload(test.payload); err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("malformed AST payload was not rejected as %q: %v", test.want, err)
			}
		})
	}
}

func appendRuleASTTestUvarint(dst []byte, value int) []byte {
	var encoded [binary.MaxVarintLen64]byte
	length := binary.PutUvarint(encoded[:], uint64(value))
	return append(dst, encoded[:length]...)
}

func TestRuleParseCacheConcurrentLoadsShareOneParse(t *testing.T) {
	const workers = 32
	cache := NewRuleParseCache("", "")
	name := "pkg/concurrent.go"
	source := []byte("package sample\nfunc Start() int { return 11 }\n")
	files := make([]*ast.File, workers)
	errs := make([]error, workers)
	start := make(chan struct{})
	var group sync.WaitGroup
	group.Add(workers)
	for index := range workers {
		go func(index int) {
			defer group.Done()
			<-start
			files[index], errs[index] = cache.loadFile(name, source)
		}(index)
	}
	close(start)
	group.Wait()
	for index, err := range errs {
		if err != nil {
			t.Fatalf("load %d failed: %v", index, err)
		}
		if files[index] != files[0] {
			t.Fatal("concurrent loads did not share a single immutable AST")
		}
	}
	if got := cache.Stats(); got.Misses != 1 || got.Writes != 0 || got.Hits != workers-1 || got.MemoryHits != workers-1 {
		t.Fatalf("concurrent source parse was not coalesced: %+v", got)
	}
}

func TestRuleParseCacheRejectsCyclicObjectScopeAndOversizedASTs(t *testing.T) {
	t.Run("cycle", func(t *testing.T) {
		file := &ast.File{Name: ast.NewIdent("sample")}
		function := &ast.FuncDecl{Name: ast.NewIdent("Start"), Type: &ast.FuncType{}}
		declaration := &ast.DeclStmt{Decl: function}
		function.Body = &ast.BlockStmt{List: []ast.Stmt{declaration}}
		file.Decls = []ast.Decl{function}
		if err := validateRuleAST(file); err == nil || !strings.Contains(err.Error(), "cycle") {
			t.Fatalf("cyclic AST was accepted: %v", err)
		}
	})

	t.Run("identifier object graph", func(t *testing.T) {
		file := &ast.File{Name: ast.NewIdent("sample")}
		file.Name.Obj = &ast.Object{Kind: ast.Var, Name: "sample"}
		if err := validateRuleAST(file); err == nil || !strings.Contains(err.Error(), "non-syntax pointer") {
			t.Fatalf("identifier object graph was accepted: %v", err)
		}
	})

	t.Run("file scope graph", func(t *testing.T) {
		file := &ast.File{Name: ast.NewIdent("sample"), Scope: &ast.Scope{}}
		if err := validateRuleAST(file); err == nil || !strings.Contains(err.Error(), "non-syntax pointer") {
			t.Fatalf("file scope graph was accepted: %v", err)
		}
	})

	t.Run("node budget", func(t *testing.T) {
		statements := make([]ast.Stmt, maxASTNodes)
		for index := range statements {
			statements[index] = &ast.EmptyStmt{}
		}
		file := &ast.File{
			Name: ast.NewIdent("sample"),
			Decls: []ast.Decl{&ast.FuncDecl{
				Name: ast.NewIdent("Start"),
				Type: &ast.FuncType{},
				Body: &ast.BlockStmt{List: statements},
			}},
		}
		if err := validateRuleAST(file); err == nil || !strings.Contains(err.Error(), "node budget") {
			t.Fatalf("oversized AST was accepted: %v", err)
		}
	})
}

func TestRuleParseCacheSharesASTButNotVMStateAndPreservesRuleSemantics(t *testing.T) {
	name := "internal/artifacts/sample/rule.go"
	source := []byte(`package sample
func Start() float64 {
	state := 2
	apply := func(delta int) int { state += delta; return state }
	first := apply(3)
	return float64(first*10 + apply(4))
}`)
	sources := map[string][]byte{name: source}
	cache := NewRuleParseCache("", "")
	one, err := compileRuleProgramCached(sources, nil, cache)
	if err != nil {
		t.Fatal(err)
	}
	two, err := compileRuleProgramCached(sources, nil, cache)
	if err != nil {
		t.Fatal(err)
	}
	fileOne := one.modules[one.entry].files[0]
	fileTwo := two.modules[two.entry].files[0]
	if fileOne != fileTwo {
		t.Fatal("compilations did not reuse the immutable source AST")
	}
	if one == two || one.modules[one.entry] == two.modules[two.entry] || one.modules[one.entry].envs[fileOne] == two.modules[two.entry].envs[fileTwo] {
		t.Fatal("compilations shared mutable program or environment state")
	}

	uncached, err := compileRuleProgram(sources, nil)
	if err != nil {
		t.Fatal(err)
	}
	vmOne, vmTwo, vmFresh := newRuleVM(one, nil, 10000), newRuleVM(two, nil, 10000), newRuleVM(uncached, nil, 10000)
	got, err := vmOne.entry("Start")
	if err != nil || got != float64(59) {
		t.Fatalf("cached VM result mismatch: got %v, want 59, error %v", got, err)
	}
	if vmOne.remaining >= 10000 || vmTwo.remaining != 10000 {
		t.Fatalf("VM evaluation state was shared: first remaining=%d, second remaining=%d", vmOne.remaining, vmTwo.remaining)
	}
	for _, vm := range []*ruleVM{vmTwo, vmFresh} {
		got, err := vm.entry("Start")
		if err != nil || got != float64(59) {
			t.Fatalf("VM parity mismatch: got %v, want 59, error %v", got, err)
		}
	}
}

func TestRuleParseCacheInvalidationBypassesBundledAndWritableEntriesOnce(t *testing.T) {
	bundleDir := t.TempDir()
	writableDir := t.TempDir()
	name := "pkg/invalidate.go"
	source := []byte("package sample\nfunc Start() int { return 12 }\n")
	seed := NewRuleParseCache("", bundleDir)
	if _, err := seed.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	cache := NewRuleParseCache(bundleDir, writableDir)
	if _, err := cache.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	if err := cache.invalidateSources(map[string][]byte{name: source}); err != nil {
		t.Fatal(err)
	}
	if _, err := cache.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	stats := cache.Stats()
	if stats.BundledHits != 1 || stats.Misses != 1 || stats.Repairs != 1 || stats.Writes != 1 {
		t.Fatalf("invalidation did not bypass both cache tiers once: %+v", stats)
	}
	if _, err := cache.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	if got := cache.Stats(); got.MemoryHits != 1 || got.Misses != 1 {
		t.Fatalf("one-shot invalidation persisted: %+v", got)
	}
}

func TestRuleParseCacheCleanupBoundsFilesAndBytes(t *testing.T) {
	t.Run("file count", func(t *testing.T) {
		dir := t.TempDir()
		live := make(map[string]struct{}, ruleParseCacheMaxFiles+3)
		for index := 0; index < ruleParseCacheMaxFiles+3; index++ {
			key := fmt.Sprintf("%064x", index+1)
			live[key] = struct{}{}
			if err := os.WriteFile(filepath.Join(dir, key+ruleParseCacheExtension), []byte("x"), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		if err := NewRuleParseCache("", dir).cleanup(live); err != nil {
			t.Fatal(err)
		}
		files := ownedCacheEntries(t, dir)
		if len(files) != ruleParseCacheMaxFiles {
			t.Fatalf("cleanup kept %d files; limit is %d", len(files), ruleParseCacheMaxFiles)
		}
	})

	t.Run("byte count and protected temp", func(t *testing.T) {
		dir := t.TempDir()
		live := map[string]struct{}{}
		for index := 0; index < 3; index++ {
			key := fmt.Sprintf("%064x", index+101)
			live[key] = struct{}{}
			file, err := os.Create(filepath.Join(dir, key+ruleParseCacheExtension))
			if err != nil {
				t.Fatal(err)
			}
			if err := file.Truncate(24 << 20); err != nil {
				_ = file.Close()
				t.Fatal(err)
			}
			if err := file.Close(); err != nil {
				t.Fatal(err)
			}
			future := time.Now().Add(time.Duration(index) * time.Second)
			if err := os.Chtimes(filepath.Join(dir, key+ruleParseCacheExtension), future, future); err != nil {
				t.Fatal(err)
			}
		}
		cache := NewRuleParseCache("", dir)
		if err := cache.cleanup(live); err != nil {
			t.Fatal(err)
		}
		files := ownedCacheEntries(t, dir)
		if len(files) != 2 || ownedCacheBytes(t, dir) > ruleParseCacheMaxBytes {
			t.Fatalf("cleanup did not enforce byte budget: files=%d bytes=%d", len(files), ownedCacheBytes(t, dir))
		}
		key := fmt.Sprintf("%064x", 999)
		protectedTemp := filepath.Join(dir, ".tmp-"+key+"-active.gttast")
		file, err := os.Create(protectedTemp)
		if err != nil {
			t.Fatal(err)
		}
		if err := file.Truncate((ruleParseCacheMaxBytes + 1)); err != nil {
			_ = file.Close()
			t.Fatal(err)
		}
		_ = file.Close()
		if err := cache.cleanup(live); err == nil || !strings.Contains(err.Error(), "protected entries exceed budget") {
			t.Fatalf("protected overflow was not reported: %v", err)
		}
		if _, err := os.Stat(protectedTemp); err != nil {
			t.Fatalf("protected temp was removed: %v", err)
		}
	})
}

func TestRuleParseCacheCleanupPreservesSymlinksAndOutsideTargets(t *testing.T) {
	cacheDir := t.TempDir()
	outsideDir := t.TempDir()
	name := "pkg/link.go"
	source := []byte("package sample\nfunc Start() int { return 1 }\n")
	key := NewRuleParseCache("", cacheDir).sourceKey(name, source)
	outside := filepath.Join(outsideDir, "outside.txt")
	if err := os.WriteFile(outside, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(cacheDir, key+ruleParseCacheExtension)
	if err := os.Symlink(outside, link); err != nil {
		if runtime.GOOS == "windows" {
			t.Skipf("Windows symlink creation is unavailable: %v", err)
		}
		t.Fatal(err)
	}
	cache := NewRuleParseCache("", cacheDir)
	if _, err := cache.loadFile(name, source); err != nil {
		t.Fatal(err)
	}
	if err := cache.cleanup(nil); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(link); err != nil {
		t.Fatalf("cache cleanup removed a symlink entry: %v", err)
	}
	if got, err := os.ReadFile(outside); err != nil || string(got) != "keep" {
		t.Fatalf("outside symlink target changed: %q, %v", got, err)
	}
}

func TestRuleParseCacheCleanupRemovesOldOrphanTempsAndKeepsProtectedTemps(t *testing.T) {
	dir := t.TempDir()
	cache := NewRuleParseCache("", dir)
	oldKey := fmt.Sprintf("%064x", 1001)
	recentKey := fmt.Sprintf("%064x", 1002)
	activeKey := fmt.Sprintf("%064x", 1003)
	oldTemp := filepath.Join(dir, ".tmp-"+oldKey+"-abandoned.gttast")
	recentTemp := filepath.Join(dir, ".tmp-"+recentKey+"-recent.gttast")
	activeTemp := filepath.Join(dir, ".tmp-"+activeKey+"-active.gttast")
	for _, path := range []string{oldTemp, recentTemp, activeTemp} {
		if err := os.WriteFile(path, []byte("temp"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	old := time.Now().Add(-2 * ruleParseCacheOrphanAge)
	if err := os.Chtimes(oldTemp, old, old); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(activeTemp, old, old); err != nil {
		t.Fatal(err)
	}
	activeKeyPath := ruleParseCacheTempPathKey(activeTemp)
	activeRuleParseCacheTemps.Store(activeKeyPath, struct{}{})
	defer activeRuleParseCacheTemps.Delete(activeKeyPath)
	if err := cache.cleanup(nil); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(oldTemp); !os.IsNotExist(err) {
		t.Fatalf("stale orphan temp was not removed: %v", err)
	}
	for _, protected := range []string{recentTemp, activeTemp} {
		if _, err := os.Stat(protected); err != nil {
			t.Fatalf("protected temp was removed: %s: %v", protected, err)
		}
	}
}

func TestRuleParseCacheRejectsJunctionOrSymlinkAncestor(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows junction behavior")
	}
	root := t.TempDir()
	outside := t.TempDir()
	cacheTarget := filepath.Join(outside, "cache")
	if err := os.Mkdir(cacheTarget, 0o700); err != nil {
		t.Fatal(err)
	}
	name := "pkg/outside.go"
	source := []byte("package sample\nfunc Start() int { return 2 }\n")
	key := NewRuleParseCache("", cacheTarget).sourceKey(name, source)
	marker := filepath.Join(cacheTarget, key+ruleParseCacheExtension)
	if err := os.WriteFile(marker, []byte("outside cache file"), 0o600); err != nil {
		t.Fatal(err)
	}
	linkParent := filepath.Join(root, "linked-parent")
	if err := createRuleParseCacheJunction(linkParent, outside); err != nil {
		t.Skipf("junction creation is unavailable: %v", err)
	}
	defer os.Remove(linkParent)
	cache := NewRuleParseCache("", filepath.Join(linkParent, "cache"))
	if err := cache.cleanup(nil); err == nil {
		t.Fatal("cleanup accepted a cache root reached through a junction")
	}
	if _, err := os.Stat(marker); err != nil {
		t.Fatalf("junction cleanup removed an outside cache file: %v", err)
	}
}

func createRuleParseCacheJunction(link, target string) error {
	command := `mklink /J "` + link + `" "` + target + `"`
	return exec.Command("cmd.exe", "/d", "/c", command).Run()
}

func ownedCacheEntries(t *testing.T, dir string) []os.DirEntry {
	t.Helper()
	all, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	var files []os.DirEntry
	for _, entry := range all {
		if _, temporary, owned := ruleParseCacheEntryKey(entry.Name()); owned && !temporary {
			files = append(files, entry)
		}
	}
	return files
}

func ownedCacheBytes(t *testing.T, dir string) int64 {
	t.Helper()
	var total int64
	for _, entry := range ownedCacheEntries(t, dir) {
		info, err := entry.Info()
		if err != nil {
			t.Fatal(err)
		}
		total += info.Size()
	}
	return total
}

func BenchmarkRuleParseCacheFreshParseVsDiskWarmDecode(b *testing.B) {
	name, source := ruleParseCacheBenchmarkSource(b)
	dir := b.TempDir()
	writer := NewRuleParseCache("", dir)
	if _, err := writer.loadFile(name, source); err != nil {
		b.Fatal(err)
	}
	parsed, err := parseRuleAST(name, source)
	if err != nil {
		b.Fatal(err)
	}
	encoded, err := encodeRuleParseCacheFile(name, source, parsed, ruleParseCacheSchema, runtime.Version())
	if err != nil {
		b.Fatal(err)
	}
	payloadStart := len(ruleParseCacheMagic) + 4 + 8
	headerSize := int(binary.BigEndian.Uint32(encoded[len(ruleParseCacheMagic) : len(ruleParseCacheMagic)+4]))
	payload := encoded[payloadStart+headerSize:]
	cacheKey := writer.sourceKey(name, source)
	cachePath := filepath.Join(dir, cacheKey+ruleParseCacheExtension)

	b.Run("fresh_parse", func(b *testing.B) {
		b.ReportAllocs()
		b.SetBytes(int64(len(source)))
		for range b.N {
			if _, err := parseRuleAST(name, source); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("memory_cache_decode", func(b *testing.B) {
		b.ReportAllocs()
		b.SetBytes(int64(len(source)))
		for range b.N {
			if _, err := decodeRuleParseCacheFile(name, source, encoded); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("syntax_payload_decode", func(b *testing.B) {
		b.ReportAllocs()
		for range b.N {
			if _, err := decodeRuleASTPayload(payload); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("syntax_payload_encode", func(b *testing.B) {
		b.ReportAllocs()
		for range b.N {
			if _, err := encodeRuleASTPayload(parsed); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("validation_only", func(b *testing.B) {
		b.ReportAllocs()
		for range b.N {
			if err := validateRuleAST(parsed); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("filesystem_path_guards", func(b *testing.B) {
		b.ReportAllocs()
		for range b.N {
			if err := ensureRuleParseCacheDir(dir, false); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("filesystem_raw_read_no_decode", func(b *testing.B) {
		b.ReportAllocs()
		b.SetBytes(int64(len(encoded)))
		for range b.N {
			if _, err := os.ReadFile(cachePath); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("filesystem_guarded_read_no_decode", func(b *testing.B) {
		b.ReportAllocs()
		b.SetBytes(int64(len(encoded)))
		for range b.N {
			if _, err := readRuleParseCacheBytesForBenchmark(dir, cachePath); err != nil {
				b.Fatal(err)
			}
		}
	})
	b.Run("disk_warm_decode", func(b *testing.B) {
		b.ReportAllocs()
		b.SetBytes(int64(len(source)))
		for range b.N {
			cache := NewRuleParseCache(dir, "")
			if _, err := cache.loadFile(name, source); err != nil {
				b.Fatal(err)
			}
		}
	})
}

// readRuleParseCacheBytesForBenchmark mirrors the production file safety and
// bounded-read checks, stopping before header checksums or AST decoding.
func readRuleParseCacheBytesForBenchmark(dir, path string) ([]byte, error) {
	if err := ensureRuleParseCacheDir(dir, false); err != nil {
		return nil, err
	}
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !safeRegularRuleParseCacheFile(info) || info.Size() < 0 || info.Size() > int64(ruleParseCacheMaxFileBytes) {
		return nil, fmt.Errorf("unsafe or oversized benchmark cache file")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	openedInfo, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if !safeRegularRuleParseCacheFile(openedInfo) || !os.SameFile(info, openedInfo) {
		return nil, fmt.Errorf("benchmark cache file changed while opening")
	}
	data, err := io.ReadAll(io.LimitReader(file, int64(ruleParseCacheMaxFileBytes+1)))
	if err != nil {
		return nil, err
	}
	if len(data) > ruleParseCacheMaxFileBytes {
		return nil, fmt.Errorf("benchmark cache file exceeds size limit")
	}
	return data, nil
}

func ruleParseCacheBenchmarkSource(b *testing.B) (string, []byte) {
	b.Helper()
	if path := os.Getenv("GTT_RULE_PARSE_BENCH_SOURCE"); path != "" {
		source, err := os.ReadFile(path)
		if err != nil {
			b.Fatal(err)
		}
		return filepath.Base(path), source
	}
	var source strings.Builder
	source.WriteString("package benchmark\n")
	for index := 0; index < 250; index++ {
		fmt.Fprintf(&source, "func Helper%d(x int) int { y := x + %d; if y%%3 == 0 { y += %d }; return y }\n", index, index+1, index%7)
	}
	source.WriteString("func Start() int { return Helper17(23) + Helper212(41) }\n")
	return "benchmark.go", []byte(source.String())
}
