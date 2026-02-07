package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
)

type requestPayload struct {
	Mode      string `json:"mode"`
	HTML      string `json:"html"`
	CarID     string `json:"car_id"`
	JS        string `json:"js"`
	ChunkType string `json:"chunk_type"`
}

func main() {
	payload, err := io.ReadAll(os.Stdin)
	if err != nil {
		fail(err)
	}
	if len(bytes.TrimSpace(payload)) == 0 {
		writeJSON(map[string]any{})
		return
	}
	var req requestPayload
	if err := json.Unmarshal(payload, &req); err != nil {
		fail(err)
	}

	switch req.Mode {
	case "", "detail":
		writeJSON(parseDetail(req.HTML, req.CarID))
	case "list-thumbs":
		writeJSON(parseListThumbs(req.HTML))
	case "chunk-parse":
		parsed, err := parseChunk(req.JS, req.ChunkType)
		if err != nil {
			fail(err)
		}
		writeJSON(parsed)
	default:
		fail(fmt.Errorf("unsupported mode: %s", req.Mode))
	}
}
