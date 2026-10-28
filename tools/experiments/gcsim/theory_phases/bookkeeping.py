"""Diagnostic-record-only delta; arithmetic/admission/replay paths stay intact."""
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('frozen record seam changed: '+old[:70])
    return text.replace(old,new,1)

def change(source):
    text=source.decode();start=text.index('func (b *NeutralBinding) r1FreezeConcrete(')
    end=text.index('\nfunc ',start+5);old=text[start:end];new=old
    new=once(new,'\tfor mi, member := range b.members {',
             '\tvar packageKey string\n\tpackageKeyReady := false\n\tfor mi, member := range b.members {')
    record='\t\t\trecord := R1FrozenPort{Package: ruleChoicesKey(choices), Seed: member.seed, Key: key, Member: mi, Owner: port.query.Owner, Dimension: dim, SourceNode: source.NodeID, SourceValue: source.Observed}'
    new=once(new,record,'''\t\t\tkeepRecord := len(b.r1Stats.Records) < 128
            var recordState, recordReason string
            var recordAnchor *float64
            recordPreserved := false''')
    # Match original branch indentation exactly; no arithmetic line is replaced.
    new=once(new,'''\t\t\t\trecord.State = "observed_package_anchor_frozen"
\t\t\t\trecord.PackageAnchorValue = &value
\t\t\t\trecord.Reason = "symbolic_dependency_unbound"''','''                if keepRecord {
                    recordState = "observed_package_anchor_frozen"
                    recordAnchor = &value
                    recordReason = "symbolic_dependency_unbound"
                }''')
    new=once(new,'''\t\t\t\trecord.State = "no_package_anchor_reference_guide"
\t\t\t\trecord.SourceSlotPreserved = true
\t\t\t\trecord.Reason = "concrete_package_response_unresolved"''','''                if keepRecord {
                    recordState = "no_package_anchor_reference_guide"
                    recordPreserved = true
                    recordReason = "concrete_package_response_unresolved"
                }''')
    new=once(new,'''\t\t\tif len(b.r1Stats.Records) < 128 {
\t\t\t\tb.r1Stats.Records = append(b.r1Stats.Records, record)''','''            if keepRecord {
                if !packageKeyReady {
                    packageKey = ruleChoicesKey(choices)
                    packageKeyReady = true
                }
                record := R1FrozenPort{Package: packageKey, Seed: member.seed, Key: key, Member: mi,
                    Owner: port.query.Owner, Dimension: dim, SourceNode: source.NodeID, SourceValue: source.Observed,
                    State: recordState, Reason: recordReason, PackageAnchorValue: recordAnchor,
                    SourceSlotPreserved: recordPreserved}
                b.r1Stats.Records = append(b.r1Stats.Records, record)''')
    legacy='package seteffects\nimport("fmt";"sort";"genshinteamstracker/native/gcsim_optimizer/internal/contracts";"genshinteamstracker/native/gcsim_optimizer/internal/formula")\n'
    legacy+=old.replace(') r1FreezeConcrete(',') r1FreezeConcreteBaseline(',1)
    return (text[:start]+new+text[end:]).encode(),legacy.encode()
