"""Profiling and opt-in exact-key candidate, only in a managed native copy."""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError("Preparation overlay anchor changed: " + before[:100])
    return text.replace(before, after, 1)


def instrument(native):
    model = native / "internal/setcontext/neutral.go"
    code = model.read_text(encoding="utf-8")
    code = replace_once(code, "type NeutralModel struct {\n",
                        "type NeutralModel struct {\n researchPrepare ResearchPrepareStats\n researchChunked bool\n")
    model.write_text(code, encoding="utf-8", newline="\n")
    cache = native / "internal/setcontext/neutral_program_cache.go"
    code = cache.read_text(encoding="utf-8")
    code = replace_once(code,
        "func (m *NeutralModel) bindConstantDimensions(values []float64) (*formula.ParametricProgram, error) {\n",
        "func (m *NeutralModel) bindConstantDimensions(values []float64) (*formula.ParametricProgram, error) {\n researchStarted := time.Now()\n")
    code = replace_once(code,
        '\tdata := make([]byte, 8*len(m.constantDimensions))\n\tfor i, dimension := range m.constantDimensions {\n\t\tbinary.LittleEndian.PutUint64(data[8*i:], math.Float64bits(values[dimension]))\n\t}\n\tkey := taggedProgramCacheKey("constant", sha256.Sum256(data))\n',
        '\tm.researchPrepare.ValidationSeconds += time.Since(researchStarted).Seconds()\n'
        '\tvar digest [32]byte\n\tif m.researchChunked {\n'
        '\t\tdigest = researchChunkedConstantDigest(values, m.constantDimensions)\n'
        '\t} else {\n\t\tdata := make([]byte, 8*len(m.constantDimensions))\n'
        '\t\tfor i, dimension := range m.constantDimensions {\n'
        '\t\t\tbinary.LittleEndian.PutUint64(data[8*i:], math.Float64bits(values[dimension]))\n'
        '\t\t}\n\t\tdigest = sha256.Sum256(data)\n\t}\n'
        '\tkey := taggedProgramCacheKey("constant", digest)\n'
        '\tm.researchPrepare.KeySeconds += time.Since(researchStarted).Seconds()\n'
        '\tm.researchPrepare.KeyBytes += 8*len(m.constantDimensions)\n')
    code = replace_once(code,
        "\t\tm.stats.ProgramHits++\n\t\treturn program, nil\n\t}\n\tm.stats.ProgramMisses++\n\tordered :=",
        "\t\tm.stats.ProgramHits++\n m.researchPrepare.HitCalls++\n m.researchPrepare.HitSeconds += time.Since(researchStarted).Seconds()\n\t\treturn program, nil\n\t}\n\tm.stats.ProgramMisses++\n researchOrderStarted := time.Now()\n\tordered :=")
    code = replace_once(code,
        "\tprogram, err := m.prepared.BindConstantEffectsRegions(ordered)\n",
        "\tm.researchPrepare.OrderSeconds += time.Since(researchOrderStarted).Seconds()\n researchRegionStarted := time.Now()\n\tprogram, err := m.prepared.BindConstantEffectsRegions(ordered)\n m.researchPrepare.RegionSeconds += time.Since(researchRegionStarted).Seconds()\n")
    code = replace_once(code,
        "\treturn program, err\n}\n\nfunc (m *NeutralModel) bindProgram",
        "\tm.researchPrepare.MissCalls++\n m.researchPrepare.MissSeconds += time.Since(researchStarted).Seconds()\n\treturn program, err\n}\n\nfunc (m *NeutralModel) bindProgram")
    code = replace_once(code, "\t\tdelete(m.programCache, old)\n",
                        "\t\tdelete(m.programCache, old)\n m.researchPrepare.Evictions++\n")
    code = replace_once(code, "\tm.programNodes += nodes\n",
                        "\tm.programNodes += nodes\n m.researchPrepare.PeakEntries = max(m.researchPrepare.PeakEntries,len(m.programCache))\n m.researchPrepare.PeakNodes = max(m.researchPrepare.PeakNodes,m.programNodes)\n")
    cache.write_text(code, encoding="utf-8", newline="\n")
    shutil.copyfile(HERE / "profile.go", native / "internal/setcontext/research_prepare_profile.go")
