package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/dop251/goja"
)

func extractExportedVar(jsText string, exportName string) string {
	re := regexp.MustCompile(`export\s*\{([^}]+)\}`)
	matches := re.FindAllStringSubmatch(jsText, -1)
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		parts := strings.Split(match[1], ",")
		for _, item := range parts {
			part := strings.TrimSpace(item)
			if part == "" {
				continue
			}
			local := part
			exported := part
			if strings.Contains(part, " as ") {
				subs := strings.SplitN(part, " as ", 2)
				local = strings.TrimSpace(subs[0])
				exported = strings.TrimSpace(subs[1])
			}
			if exported == exportName {
				return local
			}
		}
	}
	return ""
}

func extractBalanced(text string, start int) (string, int, error) {
	stack := make([]rune, 0, 8)
	inString := false
	stringChar := rune(0)
	escape := false
	for i, ch := range text[start:] {
		idx := start + i
		if inString {
			if escape {
				escape = false
				continue
			}
			if ch == '\\' {
				escape = true
				continue
			}
			if ch == stringChar {
				inString = false
			}
			continue
		}
		if ch == '"' || ch == '\'' || ch == '`' {
			inString = true
			stringChar = ch
			continue
		}
		if ch == '{' || ch == '[' {
			stack = append(stack, ch)
			continue
		}
		if ch == '}' || ch == ']' {
			if len(stack) == 0 {
				break
			}
			opening := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			if (opening == '{' && ch != '}') || (opening == '[' && ch != ']') {
				return "", 0, fmt.Errorf("mismatched bracket")
			}
			if len(stack) == 0 {
				return text[start : idx+1], idx + 1, nil
			}
		}
	}
	return "", 0, fmt.Errorf("unbalanced literal")
}

func extractAssignedLiteral(jsText string, varName string) (string, bool) {
	re := regexp.MustCompile(`\b(?:const|let|var)\s+` + regexp.QuoteMeta(varName) + `\s*=\s*`)
	loc := re.FindStringIndex(jsText)
	if loc == nil {
		return "", false
	}
	idx := loc[1]
	for idx < len(jsText) && (jsText[idx] == ' ' || jsText[idx] == '\n' || jsText[idx] == '\r' || jsText[idx] == '\t') {
		idx++
	}
	if idx >= len(jsText) {
		return "", false
	}
	if jsText[idx] != '{' && jsText[idx] != '[' {
		return "", false
	}
	lit, _, err := extractBalanced(jsText, idx)
	if err != nil {
		return "", false
	}
	return lit, true
}

func parseJSLiteral(literal string) (any, error) {
	runtime := goja.New()
	script := "JSON.stringify((" + literal + "))"
	value, err := runtime.RunString(script)
	if err != nil {
		return nil, err
	}
	var parsed any
	if err := json.Unmarshal([]byte(value.String()), &parsed); err != nil {
		return nil, err
	}
	return parsed, nil
}

func extractExportedLiteral(jsText string, exportName string) (any, bool) {
	local := extractExportedVar(jsText, exportName)
	if local == "" {
		return nil, false
	}
	literal, ok := extractAssignedLiteral(jsText, local)
	if !ok {
		return nil, false
	}
	parsed, err := parseJSLiteral(literal)
	if err != nil {
		return nil, false
	}
	return parsed, true
}

func findLargestLiteral(jsText string, startChar byte) (any, bool) {
	matchPattern := `\b(?:const|let|var)\s+[A-Za-z0-9_$]+\s*=\s*`
	re := regexp.MustCompile(matchPattern)
	locs := re.FindAllStringIndex(jsText, -1)
	bestLen := -1
	bestLiteral := ""
	for _, loc := range locs {
		idx := loc[1]
		for idx < len(jsText) && (jsText[idx] == ' ' || jsText[idx] == '\n' || jsText[idx] == '\r' || jsText[idx] == '\t') {
			idx++
		}
		if idx >= len(jsText) || jsText[idx] != startChar {
			continue
		}
		lit, _, err := extractBalanced(jsText, idx)
		if err != nil {
			continue
		}
		if len(lit) > bestLen {
			bestLen = len(lit)
			bestLiteral = lit
		}
	}
	if bestLiteral == "" {
		return nil, false
	}
	parsed, err := parseJSLiteral(bestLiteral)
	if err != nil {
		return nil, false
	}
	return parsed, true
}
