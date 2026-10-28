package main

import "strings"

func splitStage16Lines(text string) []string { return strings.Split(text,"\n") }
func isStage16Mutable(line string,wearers [4]string) bool {
 trimmed:=strings.TrimSpace(line)
 for _,w:=range wearers{
  if strings.HasPrefix(trimmed,w+" add stats ")||strings.HasPrefix(trimmed,w+" add set="){return true}
 }
 return false
}

