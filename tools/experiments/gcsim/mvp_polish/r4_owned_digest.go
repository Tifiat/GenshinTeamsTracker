package engineclient

import "os"

var r4OwnedDigest = os.Getenv("GTT_R4_OWNED_DIGEST") == "1"
