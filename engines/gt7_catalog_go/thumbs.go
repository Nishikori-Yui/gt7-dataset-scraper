package main

import (
	"regexp"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

func parseListThumbs(html string) map[string][]string {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return map[string][]string{}
	}
	thumbMap := map[string][]string{}

	doc.Find("img").Each(func(_ int, img *goquery.Selection) {
		src, ok := img.Attr("src")
		if !ok {
			return
		}
		if strings.Contains(src, "/car_thumbnails/") && strings.Contains(src, "car") {
			match := regexp.MustCompile(`(car\d+)`).FindStringSubmatch(src)
			if len(match) >= 2 {
				carID := match[1]
				thumbMap[carID] = append(thumbMap[carID], src)
			}
		}
	})

	doc.Find("a[href]").Each(func(_ int, anchor *goquery.Selection) {
		href, _ := anchor.Attr("href")
		if !strings.Contains(href, "/gt7/carlist/id/") {
			return
		}
		match := regexp.MustCompile(`/id/(car\d+)`).FindStringSubmatch(href)
		if len(match) < 2 {
			return
		}
		carID := match[1]
		imgURL := ""
		if img := anchor.Find("img").First(); img.Length() > 0 {
			if src, ok := img.Attr("src"); ok {
				imgURL = src
			}
		}
		if imgURL == "" {
			if parent := anchor.Parent(); parent.Length() > 0 {
				if img := parent.Find("img").First(); img.Length() > 0 {
					if src, ok := img.Attr("src"); ok {
						imgURL = src
					}
				}
			}
		}
		if imgURL == "" {
			style, _ := anchor.Attr("style")
			if style == "" {
				if parent := anchor.Parent(); parent.Length() > 0 {
					style, _ = parent.Attr("style")
				}
			}
			if style != "" {
				if found := regexp.MustCompile(`url\\(["']?([^"')]+)`).FindStringSubmatch(style); len(found) >= 2 {
					imgURL = found[1]
				}
			}
		}
		if imgURL != "" {
			thumbMap[carID] = append(thumbMap[carID], imgURL)
		}
	})

	out := map[string][]string{}
	for carID, urls := range thumbMap {
		out[carID] = dedupe(urls)
	}
	return out
}
