package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

var imageExtPattern = regexp.MustCompile(`(?i)\.(jpg|jpeg|png|webp)(\?|$)`)

type requestPayload struct {
	HTML  string `json:"html"`
	CarID string `json:"car_id"`
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
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

func extractIntroDetail(doc *goquery.Document) (string, string) {
	intro := ""
	detail := ""

	doc.Find("h4").EachWithBreak(func(_ int, sel *goquery.Selection) bool {
		text := strings.TrimSpace(sel.Text())
		if len([]rune(text)) < 20 {
			return true
		}
		parent := sel.Parent()
		if parent.Length() == 0 {
			return true
		}
		p := parent.Find("p").First()
		if p.Length() == 0 {
			return true
		}
		intro = text
		detail = strings.TrimSpace(p.Text())
		return false
	})

	if intro == "" {
		candidates := []string{}
		root := doc.Find("main")
		if root.Length() == 0 {
			root = doc.Selection
		}
		root.Find("p").Each(func(_ int, sel *goquery.Selection) {
			text := strings.TrimSpace(sel.Text())
			if len([]rune(text)) <= 20 {
				return
			}
			if strings.Contains(text, "Gran Turismo") || strings.Contains(text, "Car List") {
				return
			}
			candidates = append(candidates, text)
		})
		if len(candidates) > 0 {
			intro = candidates[0]
		}
		if len(candidates) > 1 {
			detail = candidates[1]
		}
	}
	return intro, detail
}

func extractSpecs(doc *goquery.Document) [][]string {
	specs := make([][]string, 0, 32)
	doc.Find("table").Each(func(_ int, table *goquery.Selection) {
		table.Find("tr").Each(func(_ int, tr *goquery.Selection) {
			cells := tr.Find("th,td")
			if cells.Length() < 2 {
				return
			}
			key := strings.TrimSpace(cells.First().Text())
			value := strings.TrimSpace(cells.Eq(1).Text())
			if key != "" && value != "" {
				specs = append(specs, []string{key, value})
			}
		})
	})
	if len(specs) > 0 {
		return specs
	}
	doc.Find("dl").Each(func(_ int, dl *goquery.Selection) {
		dt := dl.Find("dt")
		dd := dl.Find("dd")
		size := dt.Length()
		if dd.Length() < size {
			size = dd.Length()
		}
		for index := 0; index < size; index++ {
			key := strings.TrimSpace(dt.Eq(index).Text())
			value := strings.TrimSpace(dd.Eq(index).Text())
			if key != "" && value != "" {
				specs = append(specs, []string{key, value})
			}
		}
	})
	return specs
}

func extractHeroImages(html string, doc *goquery.Document, carID string) []string {
	images := make([]string, 0, 16)
	doc.Find("img").Each(func(_ int, img *goquery.Selection) {
		src, exists := img.Attr("src")
		if !exists || !looksLikeImageURL(src) {
			return
		}
		if carID != "" {
			if strings.Contains(src, carID) && !strings.Contains(src, "/car_thumbnails/") {
				images = append(images, src)
			}
			return
		}
		images = append(images, src)
	})

	if carID != "" {
		rePattern := regexp.MustCompile(fmt.Sprintf(
			`(?i)(/common/dist/gt7/carlist/assets/%s_[^"'\\s]+\\.(?:jpg|jpeg|png|webp))`,
			regexp.QuoteMeta(carID),
		))
		matches := rePattern.FindAllStringSubmatch(html, -1)
		for _, match := range matches {
			if len(match) >= 2 {
				images = append(images, match[1])
			}
		}
	}

	if len(images) == 0 {
		if meta := doc.Find(`meta[property="og:image"]`).First(); meta.Length() > 0 {
			if content, ok := meta.Attr("content"); ok {
				if carID == "" || strings.Contains(content, carID) {
					images = append(images, content)
				}
			}
		}
	}
	return dedupe(images)
}

func parseDetail(html string, carID string) map[string]any {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return map[string]any{}
	}
	data := map[string]any{}
	if name := textOrEmpty(doc.Find("h1").First()); name != "" {
		data["name"] = name
	}
	if manufacturerName := textOrEmpty(doc.Find("h2").First()); manufacturerName != "" {
		data["manufacturer_name"] = manufacturerName
	}
	intro, detail := extractIntroDetail(doc)
	if intro == "" {
		if meta := doc.Find(`meta[property="og:description"]`).First(); meta.Length() > 0 {
			if content, ok := meta.Attr("content"); ok {
				intro = strings.TrimSpace(content)
			}
		}
	}
	if intro != "" {
		data["intro"] = intro
	}
	if detail != "" {
		data["detail"] = detail
	}
	if specs := extractSpecs(doc); len(specs) > 0 {
		data["specs"] = specs
	}
	if heroes := extractHeroImages(html, doc, carID); len(heroes) > 0 {
		data["hero_images"] = heroes
	}
	return data
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
	writeJSON(parseDetail(req.HTML, req.CarID))
}

func writeJSON(value any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(value); err != nil {
		fail(err)
	}
}
