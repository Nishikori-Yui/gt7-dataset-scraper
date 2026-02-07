package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}

func parseNumber(v sql.NullString) *float64 {
	if !v.Valid {
		return nil
	}
	text := strings.TrimSpace(v.String)
	if text == "" {
		return nil
	}
	text = strings.ReplaceAll(text, "\u00a0", "")
	text = strings.ReplaceAll(text, " ", "")
	if strings.Contains(text, ",") && strings.Contains(text, ".") && strings.LastIndex(text, ",") > strings.LastIndex(text, ".") {
		text = strings.ReplaceAll(text, ".", "")
		text = strings.ReplaceAll(text, ",", ".")
	} else {
		text = strings.ReplaceAll(text, ",", "")
	}
	var b strings.Builder
	for _, ch := range text {
		if (ch >= '0' && ch <= '9') || ch == '.' || ch == '-' {
			b.WriteRune(ch)
		}
	}
	numText := b.String()
	if numText == "" || numText == "-" {
		return nil
	}
	n, err := strconv.ParseFloat(numText, 64)
	if err != nil {
		return nil
	}
	return &n
}

func writeJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		fail(err)
	}
}

func ptrString(v sql.NullString) *string {
	if !v.Valid {
		return nil
	}
	value := v.String
	return &value
}

func ptrInt64(v sql.NullInt64) *int64 {
	if !v.Valid {
		return nil
	}
	value := v.Int64
	return &value
}
