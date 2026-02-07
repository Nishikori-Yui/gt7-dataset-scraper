package main

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

var imageExtPattern = regexp.MustCompile(`(?i)\.(jpg|jpeg|png|webp)(\?|$)`)

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}

func writeJSON(value any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(value); err != nil {
		fail(err)
	}
}

func looksLikeImageURL(value string) bool {
	lower := strings.ToLower(value)
	return strings.Contains(lower, "/carlist/assets/") ||
		strings.Contains(lower, "/car_thumbnails/") ||
		imageExtPattern.MatchString(lower)
}

func textOrEmpty(sel *goquery.Selection) string {
	if sel == nil {
		return ""
	}
	return strings.TrimSpace(sel.Text())
}

func dedupe(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}
