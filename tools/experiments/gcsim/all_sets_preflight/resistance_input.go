package gttcompact

// Research-only provenance at actual compiler calls. No searching a graph for
// a coincidentally equal constant, no character/reaction label registry.
import "github.com/genshinsim/gcsim/pkg/core/info"

type ResistanceInput struct {
 NodeID uint32 `json:"node_id"`
 HitID uint64 `json:"hit_id"`
 TargetKey int `json:"target_key"`
 Element string `json:"element"`
 Resistance string `json:"resistance"`
 Observed string `json:"observed"`
}

func(c *directCompiler)resistanceInput(hit info.GTTTraceHit)compiledNode{
 n:=c.b.constant(hit.ResMod)
 c.b.resistanceInputs=append(c.b.resistanceInputs,ResistanceInput{n.id,hit.HitID,hit.TargetKey,hit.Element,decimal(hit.Resistance),decimal(hit.ResMod)})
 return n
}

// A failed formula can leave attempted nodes behind. Only return ports that
// actually feed an accepted channel; a frozen fallback does not gain a port.
func(b *nodeBuilder)usedResistanceInputs(channels []IRChannel)[]ResistanceInput{
 live:=map[uint32]bool{}
 stack:=[]uint32{}
 for _,ch:=range channels{stack=append(stack,ch.RootNodeID)}
 nodes:=map[uint32]IRNode{};for _,n:=range b.nodes{nodes[n.NodeID]=n}
 for len(stack)>0{
  id:=stack[len(stack)-1];stack=stack[:len(stack)-1];if live[id]{continue};live[id]=true
  for _,in:=range nodes[id].Inputs{stack=append(stack,in.NodeID)}
 }
 out:=[]ResistanceInput{}
 for _,p:=range b.resistanceInputs{if live[p.NodeID]{out=append(out,p)}}
 return out
}
