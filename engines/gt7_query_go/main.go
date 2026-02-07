package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fail(fmt.Errorf("usage: gt7-query-go <list|car|stats|overview> [args]"))
	}
	cmd := os.Args[1]
	args := os.Args[2:]
	switch cmd {
	case "list":
		cmdList(args)
	case "car":
		cmdCar(args)
	case "stats":
		cmdStats(args)
	case "overview":
		cmdOverview(args)
	default:
		fail(fmt.Errorf("unknown command: %s", cmd))
	}
}
