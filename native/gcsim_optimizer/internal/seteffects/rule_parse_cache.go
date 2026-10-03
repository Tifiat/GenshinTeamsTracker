package seteffects

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	ruleParseCacheSchema       = 2
	ruleParseCacheExtension    = ".gttast"
	ruleParseCacheMagic        = "GTTAST02"
	ruleParseCacheMaxHeader    = 4096
	ruleParseCacheMaxPayload   = 32 << 20
	ruleParseCacheMaxFileBytes = len(ruleParseCacheMagic) + 4 + 8 + ruleParseCacheMaxHeader + ruleParseCacheMaxPayload
	ruleParseCacheMaxDepth     = 1024
	ruleParseCacheMaxAlloc     = 64 << 20
	ruleParseCacheOrphanAge    = 24 * time.Hour
	ruleParseCacheScanLimit    = 100000
	ruleParseCacheDeleteLimit  = 10000
	ruleParseCacheChunkSize    = 256
	ruleParseCacheMaxFiles     = 512
	ruleParseCacheMaxBytes     = 64 << 20
)

var activeRuleParseCacheTemps sync.Map

type RuleParseCacheStats struct {
	Hits         uint64
	MemoryHits   uint64
	WritableHits uint64
	BundledHits  uint64
	Misses       uint64
	Repairs      uint64
	Writes       uint64
	Errors       uint64
}

// RuleParseCache retains only immutable parser output. Each compilation still
// builds its own modules, environments, globals, and VM state.
type RuleParseCache struct {
	readOnlyBundledDir string
	writableDir        string

	mu         sync.Mutex
	memory     map[string]*ast.File
	flights    map[string]*ruleParseFlight
	forceParse map[string]bool
	stats      RuleParseCacheStats
}

type ruleParseFlight struct {
	done chan struct{}
	file *ast.File
	err  error
}

type ruleParseCacheHeader struct {
	Schema        int    `json:"schema"`
	GoVersion     string `json:"go_version"`
	SourceSHA256  string `json:"source_sha256"`
	Name          string `json:"name"`
	PayloadSHA256 string `json:"payload_sha256"`
}

type ruleParseCacheOutcome struct {
	cacheHit string
	miss     bool
	repair   bool
	write    bool
	errors   uint64
}

type ruleParseCacheRead struct {
	file    *ast.File
	present bool
	invalid bool
	err     error
}

type ruleParseCacheEntry struct {
	path      string
	key       string
	temporary bool
	live      bool
	active    bool
	size      int64
	modTime   time.Time
	fileInfo  os.FileInfo
}

type ruleASTWireKind uint8

const (
	ruleASTWireInvalid ruleASTWireKind = iota
	ruleASTWireBool
	ruleASTWireSigned
	ruleASTWireUnsigned
	ruleASTWireString
	ruleASTWirePointer
	ruleASTWireNilPointer
	ruleASTWireSlice
	ruleASTWireArray
	ruleASTWireStruct
	ruleASTWireNodeInterface
	ruleASTWireNilInterface
)

type ruleASTWireField struct {
	index int
	plan  *ruleASTWirePlan
}

// Plans are compiled once from the standard-library AST types. Hot-path
// encoding/decoding follows these closures and preselected fields instead of
// rediscovering struct metadata for every AST node.
type ruleASTWirePlan struct {
	typ    reflect.Type
	kind   ruleASTWireKind
	fields []ruleASTWireField
	elem   *ruleASTWirePlan
	encode func(*ruleASTWireEncoder, reflect.Value, int) error
	decode func(*ruleASTWireDecoder, reflect.Value, int) error
}

type ruleASTWireCodec struct {
	once      sync.Once
	initErr   error
	plans     map[reflect.Type]*ruleASTWirePlan
	nodeTags  map[reflect.Type]byte
	nodeTypes []reflect.Type
}

var ruleASTWire ruleASTWireCodec

type ruleASTWireEncoder struct {
	bytes.Buffer
	nodes int
}

type ruleASTWireDecoder struct {
	data      []byte
	offset    int
	nodes     int
	allocated int64
}

func (codec *ruleASTWireCodec) initialize() {
	codec.plans = make(map[reflect.Type]*ruleASTWirePlan)
	codec.nodeTags = make(map[reflect.Type]byte)
	for _, node := range []any{
		(*ast.Comment)(nil), (*ast.CommentGroup)(nil), (*ast.Field)(nil), (*ast.FieldList)(nil),
		(*ast.BadExpr)(nil), (*ast.Ident)(nil), (*ast.Ellipsis)(nil), (*ast.BasicLit)(nil),
		(*ast.FuncLit)(nil), (*ast.CompositeLit)(nil), (*ast.ParenExpr)(nil), (*ast.SelectorExpr)(nil),
		(*ast.IndexExpr)(nil), (*ast.IndexListExpr)(nil), (*ast.SliceExpr)(nil), (*ast.TypeAssertExpr)(nil),
		(*ast.CallExpr)(nil), (*ast.StarExpr)(nil), (*ast.UnaryExpr)(nil), (*ast.BinaryExpr)(nil),
		(*ast.KeyValueExpr)(nil), (*ast.ArrayType)(nil), (*ast.StructType)(nil), (*ast.FuncType)(nil),
		(*ast.InterfaceType)(nil), (*ast.MapType)(nil), (*ast.ChanType)(nil),
		(*ast.BadStmt)(nil), (*ast.DeclStmt)(nil), (*ast.EmptyStmt)(nil), (*ast.LabeledStmt)(nil),
		(*ast.ExprStmt)(nil), (*ast.SendStmt)(nil), (*ast.IncDecStmt)(nil), (*ast.AssignStmt)(nil),
		(*ast.GoStmt)(nil), (*ast.DeferStmt)(nil), (*ast.ReturnStmt)(nil), (*ast.BranchStmt)(nil),
		(*ast.BlockStmt)(nil), (*ast.IfStmt)(nil), (*ast.CaseClause)(nil), (*ast.SwitchStmt)(nil),
		(*ast.TypeSwitchStmt)(nil), (*ast.CommClause)(nil), (*ast.SelectStmt)(nil), (*ast.ForStmt)(nil),
		(*ast.RangeStmt)(nil), (*ast.ImportSpec)(nil), (*ast.ValueSpec)(nil), (*ast.TypeSpec)(nil),
		(*ast.BadDecl)(nil), (*ast.GenDecl)(nil), (*ast.FuncDecl)(nil), (*ast.File)(nil),
	} {
		concrete := reflect.TypeOf(node)
		if len(codec.nodeTypes) >= 255 {
			codec.initErr = errors.New("too many standard AST node types for cache encoding")
			return
		}
		codec.nodeTypes = append(codec.nodeTypes, concrete)
		codec.nodeTags[concrete] = byte(len(codec.nodeTypes))
	}
	for _, nodeType := range codec.nodeTypes {
		codec.planFor(nodeType)
	}
	codec.planFor(reflect.TypeOf(ast.File{}))
}

func (codec *ruleASTWireCodec) planFor(t reflect.Type) *ruleASTWirePlan {
	if plan := codec.plans[t]; plan != nil {
		return plan
	}
	plan := &ruleASTWirePlan{typ: t}
	codec.plans[t] = plan

	switch t.Kind() {
	case reflect.Bool:
		plan.kind = ruleASTWireBool
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		plan.kind = ruleASTWireSigned
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64, reflect.Uintptr:
		plan.kind = ruleASTWireUnsigned
	case reflect.String:
		plan.kind = ruleASTWireString
	case reflect.Pointer:
		if t.Implements(reflect.TypeOf((*ast.Node)(nil)).Elem()) {
			plan.kind = ruleASTWirePointer
			plan.elem = codec.planFor(t.Elem())
		} else {
			// Object and Scope pointers are not syntax. They are allowed only as
			// nil fields, matching parser.SkipObjectResolution semantics.
			plan.kind = ruleASTWireNilPointer
		}
	case reflect.Slice:
		plan.kind = ruleASTWireSlice
		plan.elem = codec.planFor(t.Elem())
	case reflect.Array:
		plan.kind = ruleASTWireArray
		plan.elem = codec.planFor(t.Elem())
	case reflect.Struct:
		plan.kind = ruleASTWireStruct
		for index := 0; index < t.NumField(); index++ {
			field := t.Field(index)
			if field.PkgPath != "" {
				continue
			}
			plan.fields = append(plan.fields, ruleASTWireField{index: index, plan: codec.planFor(field.Type)})
		}
	case reflect.Interface:
		if t.Implements(reflect.TypeOf((*ast.Node)(nil)).Elem()) {
			plan.kind = ruleASTWireNodeInterface
		} else {
			plan.kind = ruleASTWireNilInterface
		}
	default:
		codec.initErr = fmt.Errorf("unsupported standard AST wire field type %s", t)
		return plan
	}

	plan.encode, plan.decode = codec.bind(plan)
	return plan
}

func (codec *ruleASTWireCodec) bind(plan *ruleASTWirePlan) (func(*ruleASTWireEncoder, reflect.Value, int) error, func(*ruleASTWireDecoder, reflect.Value, int) error) {
	switch plan.kind {
	case ruleASTWireBool:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if v.Bool() {
					return e.writeByte(1)
				}
				return e.writeByte(0)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				value, err := d.readByte()
				if err != nil {
					return err
				}
				if value > 1 {
					return errors.New("invalid AST boolean")
				}
				v.SetBool(value == 1)
				return nil
			}
	case ruleASTWireSigned:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				return e.writeVarint(v.Int())
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				value, err := d.readVarint()
				if err != nil {
					return err
				}
				if v.OverflowInt(value) {
					return errors.New("AST signed value overflows field")
				}
				v.SetInt(value)
				return nil
			}
	case ruleASTWireUnsigned:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				return e.writeUvarint(v.Uint())
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				value, err := d.readUvarint()
				if err != nil {
					return err
				}
				if v.OverflowUint(value) {
					return errors.New("AST unsigned value overflows field")
				}
				v.SetUint(value)
				return nil
			}
	case ruleASTWireString:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				value := v.String()
				if len(value) > ruleParseCacheMaxPayload {
					return errors.New("AST string exceeds cache payload limit")
				}
				if err := e.writeUvarint(uint64(len(value))); err != nil {
					return err
				}
				return e.writeString(value)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				size, err := d.readLength(ruleParseCacheMaxPayload)
				if err != nil {
					return err
				}
				if err := d.charge(int64(size)); err != nil {
					return err
				}
				value, err := d.readBytes(size)
				if err != nil {
					return err
				}
				v.SetString(string(value))
				return nil
			}
	case ruleASTWireNilPointer:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if !v.IsNil() {
					return fmt.Errorf("rule AST contains non-syntax pointer %s", plan.typ)
				}
				return e.writeByte(0)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				marker, err := d.readByte()
				if err != nil {
					return err
				}
				if marker != 0 {
					return fmt.Errorf("rule AST contains non-syntax pointer %s", plan.typ)
				}
				v.SetZero()
				return nil
			}
	case ruleASTWirePointer:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if v.IsNil() {
					return e.writeByte(0)
				}
				if err := e.writeByte(1); err != nil {
					return err
				}
				if err := e.countNode(); err != nil {
					return err
				}
				return plan.elem.encode(e, v.Elem(), depth+1)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				marker, err := d.readByte()
				if err != nil {
					return err
				}
				if marker == 0 {
					v.SetZero()
					return nil
				}
				if marker != 1 {
					return errors.New("invalid AST pointer marker")
				}
				if err := d.countNode(); err != nil {
					return err
				}
				if err := d.charge(int64(plan.typ.Elem().Size())); err != nil {
					return err
				}
				value := reflect.New(plan.typ.Elem())
				if err := plan.elem.decode(d, value.Elem(), depth+1); err != nil {
					return err
				}
				v.Set(value)
				return nil
			}
	case ruleASTWireSlice:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if v.IsNil() {
					return e.writeByte(0)
				}
				if err := e.writeByte(1); err != nil {
					return err
				}
				if v.Len() > maxASTNodes {
					return errors.New("AST slice length exceeds node budget")
				}
				if err := e.writeUvarint(uint64(v.Len())); err != nil {
					return err
				}
				for index := 0; index < v.Len(); index++ {
					if err := plan.elem.encode(e, v.Index(index), depth+1); err != nil {
						return err
					}
				}
				return nil
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				marker, err := d.readByte()
				if err != nil {
					return err
				}
				if marker == 0 {
					v.SetZero()
					return nil
				}
				if marker != 1 {
					return errors.New("invalid AST slice marker")
				}
				length, err := d.readLength(maxASTNodes)
				if err != nil {
					return err
				}
				// Every supported AST slice element has a non-empty wire form; this
				// bound rejects tiny corrupt payloads before allocating their slices.
				if length > d.remaining() {
					return errors.New("AST slice length exceeds remaining payload")
				}
				size := uint64(plan.typ.Elem().Size()) * uint64(length)
				if err := d.chargeUnsigned(size); err != nil {
					return err
				}
				value := reflect.MakeSlice(plan.typ, length, length)
				for index := 0; index < length; index++ {
					if err := plan.elem.decode(d, value.Index(index), depth+1); err != nil {
						return err
					}
				}
				v.Set(value)
				return nil
			}
	case ruleASTWireArray:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				for index := 0; index < v.Len(); index++ {
					if err := plan.elem.encode(e, v.Index(index), depth+1); err != nil {
						return err
					}
				}
				return nil
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				for index := 0; index < v.Len(); index++ {
					if err := plan.elem.decode(d, v.Index(index), depth+1); err != nil {
						return err
					}
				}
				return nil
			}
	case ruleASTWireStruct:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				for _, field := range plan.fields {
					if err := field.plan.encode(e, v.Field(field.index), depth+1); err != nil {
						return err
					}
				}
				return nil
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				for _, field := range plan.fields {
					if err := field.plan.decode(d, v.Field(field.index), depth+1); err != nil {
						return err
					}
				}
				return nil
			}
	case ruleASTWireNodeInterface:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if v.IsNil() {
					return e.writeByte(0)
				}
				concreteValue := v.Elem()
				if concreteValue.Kind() == reflect.Pointer && concreteValue.IsNil() {
					return errors.New("typed nil syntax AST interface")
				}
				concrete := concreteValue.Type()
				tag, ok := codec.nodeTags[concrete]
				if !ok {
					return fmt.Errorf("unregistered syntax AST node %s", concrete)
				}
				if err := e.writeByte(tag); err != nil {
					return err
				}
				return codec.plans[concrete].encode(e, concreteValue, depth+1)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				tag, err := d.readByte()
				if err != nil {
					return err
				}
				if tag == 0 {
					v.SetZero()
					return nil
				}
				if int(tag) > len(codec.nodeTypes) {
					return errors.New("invalid syntax AST node tag")
				}
				concrete := codec.nodeTypes[int(tag)-1]
				if !concrete.AssignableTo(plan.typ) {
					return errors.New("syntax AST node tag does not implement field interface")
				}
				if err := d.charge(int64(concrete.Size())); err != nil {
					return err
				}
				value := reflect.New(concrete).Elem()
				if err := codec.plans[concrete].decode(d, value, depth+1); err != nil {
					return err
				}
				if value.Kind() == reflect.Pointer && value.IsNil() {
					return errors.New("typed nil syntax AST interface")
				}
				v.Set(value)
				return nil
			}
	case ruleASTWireNilInterface:
		return func(e *ruleASTWireEncoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				if !v.IsNil() {
					return fmt.Errorf("rule AST contains non-syntax interface %s", plan.typ)
				}
				return e.writeByte(0)
			}, func(d *ruleASTWireDecoder, v reflect.Value, depth int) error {
				if err := checkRuleASTWireDepth(depth); err != nil {
					return err
				}
				marker, err := d.readByte()
				if err != nil {
					return err
				}
				if marker != 0 {
					return fmt.Errorf("rule AST contains non-syntax interface %s", plan.typ)
				}
				v.SetZero()
				return nil
			}
	default:
		return func(*ruleASTWireEncoder, reflect.Value, int) error {
				return fmt.Errorf("unsupported AST wire plan %s", plan.typ)
			}, func(*ruleASTWireDecoder, reflect.Value, int) error {
				return fmt.Errorf("unsupported AST wire plan %s", plan.typ)
			}
	}
}

func ensureRuleASTWireCodec() error {
	ruleASTWire.once.Do(ruleASTWire.initialize)
	return ruleASTWire.initErr
}

func checkRuleASTWireDepth(depth int) error {
	if depth > ruleParseCacheMaxDepth {
		return errors.New("AST wire depth limit exceeded")
	}
	return nil
}

func (encoder *ruleASTWireEncoder) writeByte(value byte) error {
	var one [1]byte
	one[0] = value
	return encoder.writeBytes(one[:])
}

func (encoder *ruleASTWireEncoder) writeBytes(value []byte) error {
	if len(value) > ruleParseCacheMaxPayload-encoder.Len() {
		return errors.New("rule AST wire payload exceeds size limit")
	}
	_, _ = encoder.Write(value)
	return nil
}

func (encoder *ruleASTWireEncoder) writeString(value string) error {
	if len(value) > ruleParseCacheMaxPayload-encoder.Len() {
		return errors.New("rule AST wire payload exceeds size limit")
	}
	_, _ = encoder.WriteString(value)
	return nil
}

func (encoder *ruleASTWireEncoder) writeUvarint(value uint64) error {
	var buf [binary.MaxVarintLen64]byte
	length := binary.PutUvarint(buf[:], value)
	return encoder.writeBytes(buf[:length])
}

func (encoder *ruleASTWireEncoder) writeVarint(value int64) error {
	var buf [binary.MaxVarintLen64]byte
	length := binary.PutVarint(buf[:], value)
	return encoder.writeBytes(buf[:length])
}

func (encoder *ruleASTWireEncoder) countNode() error {
	encoder.nodes++
	if encoder.nodes > maxASTNodes {
		return errors.New("AST wire node budget exceeded")
	}
	return nil
}

func (decoder *ruleASTWireDecoder) countNode() error {
	decoder.nodes++
	if decoder.nodes > maxASTNodes {
		return errors.New("AST wire node budget exceeded")
	}
	return nil
}

func (decoder *ruleASTWireDecoder) remaining() int { return len(decoder.data) - decoder.offset }

func (decoder *ruleASTWireDecoder) readByte() (byte, error) {
	if decoder.offset >= len(decoder.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := decoder.data[decoder.offset]
	decoder.offset++
	return value, nil
}

func (decoder *ruleASTWireDecoder) readBytes(length int) ([]byte, error) {
	if length < 0 || length > decoder.remaining() {
		return nil, io.ErrUnexpectedEOF
	}
	start := decoder.offset
	decoder.offset += length
	return decoder.data[start:decoder.offset], nil
}

func (decoder *ruleASTWireDecoder) readUvarint() (uint64, error) {
	value, size := binary.Uvarint(decoder.data[decoder.offset:])
	if size <= 0 {
		if size == 0 {
			return 0, io.ErrUnexpectedEOF
		}
		return 0, errors.New("invalid AST unsigned varint")
	}
	var canonical [binary.MaxVarintLen64]byte
	if binary.PutUvarint(canonical[:], value) != size {
		return 0, errors.New("non-canonical AST unsigned varint")
	}
	decoder.offset += size
	return value, nil
}

func (decoder *ruleASTWireDecoder) readVarint() (int64, error) {
	value, size := binary.Varint(decoder.data[decoder.offset:])
	if size <= 0 {
		if size == 0 {
			return 0, io.ErrUnexpectedEOF
		}
		return 0, errors.New("invalid AST signed varint")
	}
	var canonical [binary.MaxVarintLen64]byte
	if binary.PutVarint(canonical[:], value) != size {
		return 0, errors.New("non-canonical AST signed varint")
	}
	decoder.offset += size
	return value, nil
}

func (decoder *ruleASTWireDecoder) readLength(max int) (int, error) {
	value, err := decoder.readUvarint()
	if err != nil {
		return 0, err
	}
	if value > uint64(max) {
		return 0, errors.New("AST wire length exceeds limit")
	}
	return int(value), nil
}

func (decoder *ruleASTWireDecoder) charge(size int64) error {
	if size < 0 || size > ruleParseCacheMaxAlloc-decoder.allocated {
		return errors.New("AST wire allocation budget exceeded")
	}
	decoder.allocated += size
	return nil
}

func (decoder *ruleASTWireDecoder) chargeUnsigned(size uint64) error {
	if size > uint64(ruleParseCacheMaxAlloc) {
		return errors.New("AST wire allocation budget exceeded")
	}
	return decoder.charge(int64(size))
}

func NewRuleParseCache(readOnlyBundledDir, writableDir string) *RuleParseCache {
	return &RuleParseCache{
		readOnlyBundledDir: readOnlyBundledDir,
		writableDir:        writableDir,
		memory:             map[string]*ast.File{},
		flights:            map[string]*ruleParseFlight{},
		forceParse:         map[string]bool{},
	}
}

func (c *RuleParseCache) Stats() RuleParseCacheStats {
	if c == nil {
		return RuleParseCacheStats{}
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.stats
}

func (c *RuleParseCache) sourceKey(name string, source []byte) string {
	h := sha256.New()
	_, _ = io.WriteString(h, "gtt-rule-ast-cache\x00")
	_, _ = io.WriteString(h, fmt.Sprintf("%d\x00", ruleParseCacheSchema))
	_, _ = io.WriteString(h, runtime.Version())
	_, _ = h.Write([]byte{0})
	_, _ = io.WriteString(h, name)
	_, _ = h.Write([]byte{0})
	_, _ = h.Write(source)
	return hex.EncodeToString(h.Sum(nil))
}

func (c *RuleParseCache) loadFile(name string, source []byte) (*ast.File, error) {
	if c == nil {
		return parseRuleAST(name, source)
	}
	key := c.sourceKey(name, source)
	c.mu.Lock()
	if file := c.memory[key]; file != nil && !c.forceParse[key] {
		c.stats.Hits++
		c.stats.MemoryHits++
		c.mu.Unlock()
		return file, nil
	}
	if waiting := c.flights[key]; waiting != nil {
		c.mu.Unlock()
		<-waiting.done
		if waiting.err != nil {
			return nil, waiting.err
		}
		c.mu.Lock()
		c.stats.Hits++
		c.stats.MemoryHits++
		c.mu.Unlock()
		return waiting.file, nil
	}
	force := c.forceParse[key]
	delete(c.forceParse, key)
	delete(c.memory, key)
	flight := &ruleParseFlight{done: make(chan struct{})}
	c.flights[key] = flight
	c.mu.Unlock()

	file, outcome, err := c.loadFileLeader(name, source, key, force)
	c.mu.Lock()
	if err == nil {
		c.memory[key] = file
	}
	if outcome.cacheHit != "" {
		c.stats.Hits++
		switch outcome.cacheHit {
		case "writable":
			c.stats.WritableHits++
		case "bundled":
			c.stats.BundledHits++
		}
	}
	if outcome.miss {
		c.stats.Misses++
	}
	if outcome.repair {
		c.stats.Repairs++
	}
	if outcome.write {
		c.stats.Writes++
	}
	c.stats.Errors += outcome.errors
	flight.file, flight.err = file, err
	delete(c.flights, key)
	close(flight.done)
	c.mu.Unlock()
	return file, err
}

func (c *RuleParseCache) loadFileLeader(name string, source []byte, key string, force bool) (*ast.File, ruleParseCacheOutcome, error) {
	var outcome ruleParseCacheOutcome
	if !force {
		for _, candidate := range []struct {
			dir   string
			label string
		}{{c.writableDir, "writable"}, {c.readOnlyBundledDir, "bundled"}} {
			if candidate.dir == "" || candidate.label == "writable" && c.sameCacheDirectory(c.writableDir, c.readOnlyBundledDir) {
				continue
			}
			read := readRuleParseCacheFile(candidate.dir, name, source, key)
			if read.err != nil {
				outcome.errors++
				if read.invalid {
					outcome.repair = true
					// A damaged writable entry shadows any older bundled copy. Reparse
					// verified source bytes and repair the writable copy atomically.
					if candidate.label == "writable" {
						break
					}
				}
				continue
			}
			if read.file != nil {
				outcome.cacheHit = candidate.label
				return read.file, outcome, nil
			}
		}
	}
	outcome.miss = true
	file, err := parseRuleAST(name, source)
	if err != nil {
		outcome.errors++
		return nil, outcome, err
	}
	if err := validateRuleAST(file); err != nil {
		outcome.errors++
		return nil, outcome, err
	}
	if c.writableDir != "" && !c.sameCacheDirectory(c.writableDir, c.readOnlyBundledDir) {
		if err := writeRuleParseCacheFile(c.writableDir, name, source, key, file); err != nil {
			outcome.errors++
		} else {
			outcome.write = true
		}
	}
	return file, outcome, nil
}

func parseRuleAST(name string, source []byte) (*ast.File, error) {
	file, err := parser.ParseFile(token.NewFileSet(), name, source, parser.SkipObjectResolution)
	if err != nil {
		return nil, err
	}
	return file, nil
}

// invalidateSources prepares one fresh parse per verified source key. It
// bypasses both cache tiers on the next load and removes only matching regular
// writable entries; immutable bundled entries are never touched.
func (c *RuleParseCache) invalidateSources(sources map[string][]byte) error {
	if c == nil {
		return nil
	}
	keys := make([]string, 0, len(sources))
	seen := map[string]bool{}
	for name, source := range sources {
		key := c.sourceKey(name, source)
		if !seen[key] {
			seen[key] = true
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	var errs []error
	for _, key := range keys {
		c.mu.Lock()
		delete(c.memory, key)
		c.forceParse[key] = true
		flight := c.flights[key]
		c.stats.Repairs++
		c.mu.Unlock()
		if flight != nil {
			<-flight.done
		}
		c.mu.Lock()
		delete(c.memory, key)
		c.forceParse[key] = true
		c.mu.Unlock()
		if err := c.removeWritableEntry(key); err != nil {
			c.mu.Lock()
			c.stats.Errors++
			c.mu.Unlock()
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

func (c *RuleParseCache) removeWritableEntry(key string) error {
	if c.writableDir == "" || c.sameCacheDirectory(c.writableDir, c.readOnlyBundledDir) {
		return nil
	}
	if !validRuleParseCacheKey(key) {
		return errors.New("invalid rule parse cache key")
	}
	if err := ensureRuleParseCacheDir(c.writableDir, false); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	}
	path := filepath.Join(c.writableDir, key+ruleParseCacheExtension)
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if !safeRegularRuleParseCacheFile(info) {
		return errors.New("refusing to remove non-regular rule parse cache entry")
	}
	return os.Remove(path)
}

func (c *RuleParseCache) cleanup(liveKeys map[string]struct{}) (retErr error) {
	if c == nil {
		return nil
	}
	defer func() {
		if retErr != nil {
			c.mu.Lock()
			c.stats.Errors++
			c.mu.Unlock()
		}
	}()
	c.mu.Lock()
	for key := range c.memory {
		if _, live := liveKeys[key]; !live {
			delete(c.memory, key)
		}
	}
	for key := range c.forceParse {
		if _, live := liveKeys[key]; !live {
			delete(c.forceParse, key)
		}
	}
	c.mu.Unlock()
	if c.writableDir == "" || c.sameCacheDirectory(c.writableDir, c.readOnlyBundledDir) {
		return nil
	}
	if err := ensureRuleParseCacheDir(c.writableDir, false); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	}
	dir, err := os.Open(c.writableDir)
	if err != nil {
		return err
	}
	defer dir.Close()

	entries := make([]ruleParseCacheEntry, 0)
	scanned := 0
	for {
		remaining := ruleParseCacheScanLimit - scanned
		chunkSize := ruleParseCacheChunkSize
		if remaining <= 0 {
			chunkSize = 1
		} else if remaining < chunkSize {
			chunkSize = remaining
		}
		batch, readErr := dir.ReadDir(chunkSize)
		if remaining <= 0 && len(batch) != 0 {
			return errors.New("rule parse cache cleanup scan limit reached")
		}
		scanned += len(batch)
		for _, entry := range batch {
			key, temporary, owned := ruleParseCacheEntryKey(entry.Name())
			if !owned {
				continue
			}
			fullPath := filepath.Join(c.writableDir, entry.Name())
			info, statErr := os.Lstat(fullPath)
			if statErr != nil || !safeRegularRuleParseCacheFile(info) {
				continue
			}
			_, live := liveKeys[key]
			active := temporary && activeRuleParseCacheTemp(fullPath)
			if temporary && !active && time.Since(info.ModTime()) >= ruleParseCacheOrphanAge {
				entries = append(entries, ruleParseCacheEntry{path: fullPath, key: key, temporary: true, size: info.Size(), modTime: info.ModTime(), fileInfo: info})
				continue
			}
			entries = append(entries, ruleParseCacheEntry{path: fullPath, key: key, temporary: temporary, live: live, active: active, size: info.Size(), modTime: info.ModTime(), fileInfo: info})
		}
		if errors.Is(readErr, io.EOF) {
			break
		}
		if readErr != nil {
			return readErr
		}
		if len(batch) == 0 {
			break
		}
	}

	var stale, protectedTemps, liveEntries []ruleParseCacheEntry
	for _, entry := range entries {
		if entry.temporary {
			if entry.active || time.Since(entry.modTime) < ruleParseCacheOrphanAge {
				protectedTemps = append(protectedTemps, entry)
			} else {
				stale = append(stale, entry)
			}
		} else if entry.live {
			liveEntries = append(liveEntries, entry)
		} else {
			stale = append(stale, entry)
		}
	}
	sort.Slice(liveEntries, func(i, j int) bool {
		if liveEntries[i].modTime.Equal(liveEntries[j].modTime) {
			return liveEntries[i].path < liveEntries[j].path
		}
		return liveEntries[i].modTime.After(liveEntries[j].modTime)
	})
	keptCount, keptBytes := len(protectedTemps), int64(0)
	for _, entry := range protectedTemps {
		keptBytes += entry.size
	}
	for _, entry := range liveEntries {
		if keptCount < ruleParseCacheMaxFiles && keptBytes+entry.size <= ruleParseCacheMaxBytes {
			keptCount++
			keptBytes += entry.size
		} else {
			stale = append(stale, entry)
		}
	}
	sort.Slice(stale, func(i, j int) bool {
		if stale[i].modTime.Equal(stale[j].modTime) {
			return stale[i].path < stale[j].path
		}
		return stale[i].modTime.Before(stale[j].modTime)
	})
	deleteLimitHit := len(stale) > ruleParseCacheDeleteLimit
	if deleteLimitHit {
		stale = stale[:ruleParseCacheDeleteLimit]
	}
	for _, entry := range stale {
		if err := removeOwnedRuleParseCacheFile(c.writableDir, entry); err != nil {
			return err
		}
	}
	if deleteLimitHit {
		return errors.New("rule parse cache cleanup deletion limit reached")
	}
	if len(protectedTemps) > ruleParseCacheMaxFiles || keptBytes > ruleParseCacheMaxBytes {
		return fmt.Errorf("rule parse cache protected entries exceed budget: %d files, %d bytes", len(protectedTemps), keptBytes)
	}
	return nil
}

func removeOwnedRuleParseCacheFile(dir string, entry ruleParseCacheEntry) error {
	if err := ensureRuleParseCacheDir(dir, false); err != nil {
		return err
	}
	info, err := os.Lstat(entry.path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if !safeRegularRuleParseCacheFile(info) || info.Size() != entry.size || entry.fileInfo == nil || !os.SameFile(entry.fileInfo, info) {
		return nil
	}
	if !entry.temporary {
		key, temporary, owned := ruleParseCacheEntryKey(filepath.Base(entry.path))
		if !owned || temporary || key != entry.key {
			return nil
		}
	} else {
		key, temporary, owned := ruleParseCacheEntryKey(filepath.Base(entry.path))
		if !owned || !temporary || key != entry.key {
			return nil
		}
	}
	return os.Remove(entry.path)
}

func (c *RuleParseCache) sameCacheDirectory(left, right string) bool {
	if left == "" || right == "" {
		return false
	}
	a, errA := filepath.Abs(filepath.Clean(left))
	b, errB := filepath.Abs(filepath.Clean(right))
	if errA != nil || errB != nil {
		return filepath.Clean(left) == filepath.Clean(right)
	}
	if runtime.GOOS == "windows" {
		return strings.EqualFold(filepath.Clean(a), filepath.Clean(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}

func readRuleParseCacheFile(dir, name string, source []byte, key string) ruleParseCacheRead {
	path := filepath.Join(dir, key+ruleParseCacheExtension)
	if err := ensureRuleParseCacheDir(dir, false); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return ruleParseCacheRead{}
		}
		return ruleParseCacheRead{present: true, err: err}
	}
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return ruleParseCacheRead{}
	}
	if err != nil {
		return ruleParseCacheRead{present: true, err: err}
	}
	if !safeRegularRuleParseCacheFile(info) {
		return ruleParseCacheRead{present: true, err: errors.New("unsafe rule parse cache entry")}
	}
	if info.Size() < 0 || info.Size() > int64(ruleParseCacheMaxFileBytes) {
		return ruleParseCacheRead{present: true, invalid: true, err: errors.New("rule parse cache file size is invalid")}
	}
	file, err := os.Open(path)
	if err != nil {
		return ruleParseCacheRead{present: true, err: err}
	}
	defer file.Close()
	openedInfo, err := file.Stat()
	if err != nil || !safeRegularRuleParseCacheFile(openedInfo) || !os.SameFile(info, openedInfo) {
		if err == nil {
			err = errors.New("rule parse cache entry changed while opening")
		}
		return ruleParseCacheRead{present: true, err: err}
	}
	data, err := io.ReadAll(io.LimitReader(file, int64(ruleParseCacheMaxFileBytes+1)))
	if err != nil {
		return ruleParseCacheRead{present: true, err: err}
	}
	if len(data) > ruleParseCacheMaxFileBytes {
		return ruleParseCacheRead{present: true, invalid: true, err: errors.New("rule parse cache file exceeds size limit")}
	}
	astFile, err := decodeRuleParseCacheFile(name, source, data)
	if err != nil {
		return ruleParseCacheRead{present: true, invalid: true, err: err}
	}
	return ruleParseCacheRead{file: astFile, present: true}
}

func writeRuleParseCacheFile(dir, name string, source []byte, key string, file *ast.File) error {
	if !validRuleParseCacheKey(key) {
		return errors.New("invalid rule parse cache key")
	}
	data, err := encodeRuleParseCacheFile(name, source, file, ruleParseCacheSchema, runtime.Version())
	if err != nil {
		return err
	}
	if err := ensureRuleParseCacheDir(dir, true); err != nil {
		return err
	}
	temp, err := os.CreateTemp(dir, ".tmp-"+key+"-*.gttast")
	if err != nil {
		return err
	}
	tempPath := temp.Name()
	activeTempKey := ruleParseCacheTempPathKey(tempPath)
	activeRuleParseCacheTemps.Store(activeTempKey, struct{}{})
	defer activeRuleParseCacheTemps.Delete(activeTempKey)
	removeTemp := true
	defer func() {
		if removeTemp {
			_ = temp.Close()
			_ = os.Remove(tempPath)
		}
	}()
	if _, err := temp.Write(data); err != nil {
		return err
	}
	if err := temp.Sync(); err != nil {
		return err
	}
	if err := temp.Close(); err != nil {
		return err
	}
	target := filepath.Join(dir, key+ruleParseCacheExtension)
	if info, err := os.Lstat(target); err == nil {
		if !safeRegularRuleParseCacheFile(info) {
			return errors.New("refusing to replace non-regular rule parse cache entry")
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := os.Rename(tempPath, target); err != nil {
		return err
	}
	removeTemp = false
	return nil
}

func encodeRuleParseCacheFile(name string, source []byte, file *ast.File, schema int, goVersion string) ([]byte, error) {
	if err := validateRuleAST(file); err != nil {
		return nil, err
	}
	payload, err := encodeRuleASTPayload(file)
	if err != nil {
		return nil, err
	}
	if len(payload) > ruleParseCacheMaxPayload {
		return nil, errors.New("rule parse cache payload exceeds size limit")
	}
	header := ruleParseCacheHeader{
		Schema:        schema,
		GoVersion:     goVersion,
		SourceSHA256:  sha256Hex(source),
		Name:          name,
		PayloadSHA256: sha256Hex(payload),
	}
	headerBytes, err := json.Marshal(header)
	if err != nil {
		return nil, err
	}
	if len(headerBytes) > ruleParseCacheMaxHeader {
		return nil, errors.New("rule parse cache header exceeds size limit")
	}
	var output bytes.Buffer
	output.Grow(len(ruleParseCacheMagic) + 4 + 8 + len(headerBytes) + len(payload))
	output.WriteString(ruleParseCacheMagic)
	_ = binary.Write(&output, binary.BigEndian, uint32(len(headerBytes)))
	_ = binary.Write(&output, binary.BigEndian, uint64(len(payload)))
	output.Write(headerBytes)
	output.Write(payload)
	return output.Bytes(), nil
}

func decodeRuleParseCacheFile(name string, source []byte, data []byte) (*ast.File, error) {
	prefixSize := len(ruleParseCacheMagic) + 4 + 8
	if len(data) < prefixSize || string(data[:len(ruleParseCacheMagic)]) != ruleParseCacheMagic {
		return nil, errors.New("invalid rule parse cache magic")
	}
	offset := len(ruleParseCacheMagic)
	headerSize := binary.BigEndian.Uint32(data[offset : offset+4])
	offset += 4
	payloadSize := binary.BigEndian.Uint64(data[offset : offset+8])
	offset += 8
	if headerSize == 0 || headerSize > ruleParseCacheMaxHeader || payloadSize > ruleParseCacheMaxPayload {
		return nil, errors.New("rule parse cache length is invalid")
	}
	if uint64(len(data)-offset) != uint64(headerSize)+payloadSize {
		return nil, errors.New("rule parse cache length mismatch")
	}
	var header ruleParseCacheHeader
	if err := json.Unmarshal(data[offset:offset+int(headerSize)], &header); err != nil {
		return nil, err
	}
	offset += int(headerSize)
	payload := data[offset:]
	if header.Schema != ruleParseCacheSchema || header.GoVersion != runtime.Version() || header.Name != name || header.SourceSHA256 != sha256Hex(source) {
		return nil, errors.New("rule parse cache source or schema mismatch")
	}
	if header.PayloadSHA256 != sha256Hex(payload) {
		return nil, errors.New("rule parse cache payload checksum mismatch")
	}
	return decodeRuleASTPayload(payload)
}

func encodeRuleASTPayload(file *ast.File) ([]byte, error) {
	if file == nil {
		return nil, errors.New("cannot encode nil rule AST")
	}
	if err := ensureRuleASTWireCodec(); err != nil {
		return nil, err
	}
	encoder := &ruleASTWireEncoder{nodes: 1}
	if encoder.nodes > maxASTNodes {
		return nil, errors.New("AST wire node budget exceeded")
	}
	fileType := reflect.TypeOf(ast.File{})
	if err := ruleASTWire.plans[fileType].encode(encoder, reflect.ValueOf(*file), 0); err != nil {
		return nil, err
	}
	return encoder.Bytes(), nil
}

func decodeRuleASTPayload(payload []byte) (*ast.File, error) {
	if len(payload) > ruleParseCacheMaxPayload {
		return nil, errors.New("rule AST wire payload exceeds size limit")
	}
	if err := ensureRuleASTWireCodec(); err != nil {
		return nil, err
	}
	file := &ast.File{}
	decoder := &ruleASTWireDecoder{
		data:      payload,
		nodes:     1,
		allocated: int64(reflect.TypeOf(ast.File{}).Size()),
	}
	if decoder.nodes > maxASTNodes {
		return nil, errors.New("AST wire node budget exceeded")
	}
	fileType := reflect.TypeOf(ast.File{})
	if err := ruleASTWire.plans[fileType].decode(decoder, reflect.ValueOf(file).Elem(), 0); err != nil {
		return nil, err
	}
	if decoder.offset != len(payload) {
		return nil, errors.New("rule AST wire payload has trailing bytes")
	}
	if file.Name == nil {
		return nil, errors.New("rule AST wire payload has no package name")
	}
	return file, nil
}

func validateRuleAST(file *ast.File) error {
	if file == nil || file.Name == nil {
		return errors.New("rule parse cache has no file or package name")
	}
	if err := validateRuleASTGraph(file); err != nil {
		return err
	}
	count := 0
	ast.Inspect(file, func(node ast.Node) bool {
		if node != nil {
			count++
		}
		return count <= maxASTNodes
	})
	if count > maxASTNodes {
		return errors.New("rule parse cache AST node budget exceeded")
	}
	return nil
}

func validateRuleASTGraph(file *ast.File) error {
	nodeType := reflect.TypeOf((*ast.Node)(nil)).Elem()
	type frame struct {
		value reflect.Value
		ptr   uintptr
		exit  bool
	}
	stack := []frame{{value: reflect.ValueOf(file)}}
	active := map[uintptr]bool{}
	visited := map[uintptr]bool{}
	for len(stack) != 0 {
		last := len(stack) - 1
		current := stack[last]
		stack = stack[:last]
		if current.exit {
			delete(active, current.ptr)
			continue
		}
		value := current.value
		if !value.IsValid() {
			continue
		}
		switch value.Kind() {
		case reflect.Interface:
			if !value.IsNil() {
				stack = append(stack, frame{value: value.Elem()})
			}
		case reflect.Pointer:
			if value.IsNil() {
				continue
			}
			if !value.Type().Implements(nodeType) {
				return fmt.Errorf("rule AST contains non-syntax pointer %s", value.Type())
			}
			ptr := value.Pointer()
			if active[ptr] {
				return errors.New("rule AST contains a pointer cycle")
			}
			if visited[ptr] {
				continue
			}
			visited[ptr] = true
			if len(visited) > maxASTNodes {
				return errors.New("rule AST node budget exceeded")
			}
			active[ptr] = true
			stack = append(stack, frame{ptr: ptr, exit: true}, frame{value: value.Elem()})
		case reflect.Struct:
			for index := value.NumField() - 1; index >= 0; index-- {
				if value.Type().Field(index).PkgPath == "" {
					stack = append(stack, frame{value: value.Field(index)})
				}
			}
		case reflect.Slice, reflect.Array:
			for index := value.Len() - 1; index >= 0; index-- {
				stack = append(stack, frame{value: value.Index(index)})
			}
		}
	}
	return nil
}

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func validRuleParseCacheKey(key string) bool {
	if len(key) != sha256.Size*2 {
		return false
	}
	for _, char := range key {
		if !(char >= '0' && char <= '9' || char >= 'a' && char <= 'f') {
			return false
		}
	}
	return true
}

func ruleParseCacheEntryKey(name string) (key string, temporary, owned bool) {
	if strings.HasSuffix(name, ruleParseCacheExtension) {
		stem := strings.TrimSuffix(name, ruleParseCacheExtension)
		if validRuleParseCacheKey(stem) {
			return stem, false, true
		}
		const tempPrefix = ".tmp-"
		if strings.HasPrefix(stem, tempPrefix) {
			rest := strings.TrimPrefix(stem, tempPrefix)
			separator := strings.IndexByte(rest, '-')
			if separator > 0 {
				key = rest[:separator]
				suffix := rest[separator+1:]
				if validRuleParseCacheKey(key) && suffix != "" && safeCacheTempSuffix(suffix) {
					return key, true, true
				}
			}
		}
	}
	return "", false, false
}

func safeCacheTempSuffix(suffix string) bool {
	for _, char := range suffix {
		if !(char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9' || char == '_' || char == '-') {
			return false
		}
	}
	return true
}

func activeRuleParseCacheTemp(path string) bool {
	_, ok := activeRuleParseCacheTemps.Load(ruleParseCacheTempPathKey(path))
	return ok
}

func ruleParseCacheTempPathKey(path string) string {
	absPath, err := filepath.Abs(path)
	if err != nil {
		absPath = filepath.Clean(path)
	}
	if runtime.GOOS == "windows" {
		absPath = strings.ToLower(absPath)
	}
	return absPath
}

func ensureRuleParseCacheDir(dir string, create bool) error {
	if dir == "" {
		return errors.New("empty rule parse cache directory")
	}
	absPath, err := filepath.Abs(filepath.Clean(dir))
	if err != nil {
		return err
	}
	if create {
		if err := checkRuleParseCachePathComponents(absPath, true); err != nil {
			return err
		}
		if err := os.MkdirAll(absPath, 0o700); err != nil {
			return err
		}
	}
	return checkRuleParseCachePathComponents(absPath, false)
}

func checkRuleParseCachePathComponents(absPath string, allowMissing bool) error {
	volume := filepath.VolumeName(absPath)
	rest := strings.TrimPrefix(absPath, volume)
	current := string(os.PathSeparator)
	if volume != "" {
		current = volume + string(os.PathSeparator)
	}
	rootInfo, err := os.Lstat(current)
	if err != nil {
		return err
	}
	if !rootInfo.IsDir() || rootInfo.Mode()&os.ModeSymlink != 0 || hasRuleParseCacheReparsePoint(rootInfo) {
		return errors.New("unsafe rule parse cache ancestor")
	}
	for _, component := range strings.FieldsFunc(rest, func(char rune) bool { return char == os.PathSeparator }) {
		current = filepath.Join(current, component)
		info, err := os.Lstat(current)
		if errors.Is(err, os.ErrNotExist) && allowMissing {
			continue
		}
		if err != nil {
			return err
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || hasRuleParseCacheReparsePoint(info) {
			return errors.New("unsafe rule parse cache ancestor")
		}
	}
	return nil
}

func safeRegularRuleParseCacheFile(info os.FileInfo) bool {
	return info != nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 && !hasRuleParseCacheReparsePoint(info)
}

func hasRuleParseCacheReparsePoint(info os.FileInfo) bool {
	if info == nil || runtime.GOOS != "windows" {
		return false
	}
	value := reflect.ValueOf(info.Sys())
	if !value.IsValid() {
		return false
	}
	if value.Kind() == reflect.Pointer {
		if value.IsNil() {
			return false
		}
		value = value.Elem()
	}
	if value.Kind() != reflect.Struct {
		return false
	}
	attributes := value.FieldByName("FileAttributes")
	return attributes.IsValid() && attributes.CanUint() && attributes.Uint()&0x400 != 0 // FILE_ATTRIBUTE_REPARSE_POINT
}
