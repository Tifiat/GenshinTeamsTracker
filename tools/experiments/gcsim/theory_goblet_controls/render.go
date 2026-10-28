// Scratch-only renderer; production rendering and numerical bodies are unchanged.
package finalists

import (
 "fmt"
 "strings"

 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

// RenderStage16 receives an already completely replaced package context.
// Only artifact stat rows and the simulation budget may change.
func RenderStage16(config string, wearers [4]string, state alloc.State) (RenderedConfig, error) {
 if err := alloc.ValidateFull45(state); err != nil { return RenderedConfig{}, err }
 keys, values, mainValues := alloc.StatKeys(), alloc.StatValues(), alloc.MainValues()
 rolls := state.Rolls()
 for actor, wearer := range wearers {
  stats := map[string]float64{}
  for _, main := range state.Mains[actor] { stats[main] += mainValues[main] }
  for j, units := range rolls[actor] { stats[keys[j]] += units * values[j] }
  body, err := formatStats(stats)
  if err != nil { return RenderedConfig{}, err }
  var count int
  config, count, err = replaceActorLine(config, wearer, "stats", fmt.Sprintf("%s add stats %s;", wearer, body))
  if err != nil || count != 1 { return RenderedConfig{}, fmt.Errorf("Stage16 stat row %s count%d: %v",wearer,count,err) }
 }
 text, err := setSimulationOptions(config,1,1)
 if err != nil { return RenderedConfig{},err }
 return RenderedConfig{Text:text,SHA256:contracts.TextSHA256(text)},nil
}

// Stage16Invariant strips only explicit mutable rows. Its hash preserves
// declaration/weapon/rotation/target/energy/settings outside iteration/workers.
func Stage16Invariant(config string, wearers [4]string) (string,error) {
 var err error
 for _, wearer := range wearers {
  var count int
  config,count,err=replaceActorLine(config,wearer,"stats",wearer+" add stats <artifact>;")
  if err!=nil||count!=1{return "",fmt.Errorf("Stage16 invariant stats")}
  // setcontext.Replace inserts complete package rows at the existing stats row.
  lines:=strings.Split(config,"\n")
  filtered:=make([]string,0,len(lines))
  for _,line:=range lines {
   if strings.HasPrefix(strings.TrimSpace(line),wearer+" add set="){continue}
   filtered=append(filtered,line)
  }
  config=strings.Join(filtered,"\n")
 }
 config,err=setSimulationOptions(config,1,1)
 if err!=nil{return "",err}
 return contracts.TextSHA256(config),nil
}

