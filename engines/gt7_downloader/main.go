package main

import (
	"bufio"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type Job struct {
	JobID   string `json:"job_id"`
	URL     string `json:"url"`
	DestRel string `json:"dest_rel"`
}

type Result struct {
	JobID   string `json:"job_id"`
	URL     string `json:"url"`
	DestRel string `json:"dest_rel"`
	Status  string `json:"status"`
	PathRel string `json:"path_rel,omitempty"`
	Bytes   int64  `json:"bytes,omitempty"`
	Error   string `json:"error,omitempty"`
}

func normalizeImageExt(ext string) string {
	lower := strings.ToLower(strings.TrimSpace(ext))
	if lower == "" {
		return ""
	}
	if lower == ".jpeg" || lower == ".jpe" {
		return ".jpg"
	}
	return lower
}

func sanitizeRelativePath(p string) (string, error) {
	if p == "" {
		return "", errors.New("dest_rel is empty")
	}
	clean := filepath.Clean(strings.ReplaceAll(p, "\\", "/"))
	if strings.HasPrefix(clean, "/") || strings.HasPrefix(clean, "../") || clean == ".." {
		return "", fmt.Errorf("invalid dest_rel: %s", p)
	}
	return clean, nil
}

func extFromContentType(contentType string) string {
	if contentType == "" {
		return ""
	}
	base := strings.TrimSpace(strings.Split(contentType, ";")[0])
	if base == "" {
		return ""
	}
	exts, err := mime.ExtensionsByType(base)
	if err != nil || len(exts) == 0 {
		return ""
	}
	chosen := ""
	for _, ext := range exts {
		norm := normalizeImageExt(ext)
		if norm == ".jpg" {
			return norm
		}
		if chosen == "" {
			chosen = norm
		}
	}
	return chosen
}

func extFromURL(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	ext := filepath.Ext(parsed.Path)
	if ext == "" {
		return ""
	}
	return normalizeImageExt(ext)
}

func chooseFinalPath(baseDir, destRel, rawURL, contentType string) (string, string) {
	cleanRel, _ := sanitizeRelativePath(destRel)
	ext := normalizeImageExt(filepath.Ext(cleanRel))
	if ext == "" {
		ext = extFromContentType(contentType)
	}
	if ext == "" {
		ext = extFromURL(rawURL)
	}
	if ext == "" {
		ext = ".jpg"
	}
	finalRel := cleanRel
	if filepath.Ext(finalRel) == "" {
		finalRel = finalRel + ext
	}
	finalAbs := filepath.Join(baseDir, finalRel)
	return finalAbs, filepath.ToSlash(finalRel)
}

func ensureParent(path string) error {
	parent := filepath.Dir(path)
	return os.MkdirAll(parent, 0o755)
}

func downloadOnce(client *http.Client, baseDir string, job Job) Result {
	result := Result{
		JobID:   job.JobID,
		URL:     job.URL,
		DestRel: job.DestRel,
	}
	cleanRel, err := sanitizeRelativePath(job.DestRel)
	if err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	finalAbs, finalRel := chooseFinalPath(baseDir, cleanRel, job.URL, "")
	if _, statErr := os.Stat(finalAbs); statErr == nil {
		result.Status = "skipped"
		result.PathRel = finalRel
		return result
	}
	req, err := http.NewRequest(http.MethodGet, job.URL, nil)
	if err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	resp, err := client.Do(req)
	if err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		result.Status = "error"
		result.Error = fmt.Sprintf("http %d", resp.StatusCode)
		return result
	}
	finalAbs, finalRel = chooseFinalPath(baseDir, cleanRel, job.URL, resp.Header.Get("Content-Type"))
	if _, statErr := os.Stat(finalAbs); statErr == nil {
		result.Status = "skipped"
		result.PathRel = finalRel
		return result
	}
	if err := ensureParent(finalAbs); err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	tmp := finalAbs + ".part"
	f, err := os.Create(tmp)
	if err != nil {
		result.Status = "error"
		result.Error = err.Error()
		return result
	}
	n, copyErr := io.Copy(f, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		_ = os.Remove(tmp)
		result.Status = "error"
		result.Error = copyErr.Error()
		return result
	}
	if closeErr != nil {
		_ = os.Remove(tmp)
		result.Status = "error"
		result.Error = closeErr.Error()
		return result
	}
	if renameErr := os.Rename(tmp, finalAbs); renameErr != nil {
		_ = os.Remove(tmp)
		result.Status = "error"
		result.Error = renameErr.Error()
		return result
	}
	result.Status = "ok"
	result.PathRel = finalRel
	result.Bytes = n
	return result
}

func processWithRetry(client *http.Client, baseDir string, job Job, retries int) Result {
	attempts := retries + 1
	var last Result
	for idx := 0; idx < attempts; idx++ {
		res := downloadOnce(client, baseDir, job)
		if res.Status == "ok" || res.Status == "skipped" {
			return res
		}
		last = res
	}
	return last
}

func readJobs(stdin io.Reader) ([]Job, error) {
	scanner := bufio.NewScanner(stdin)
	scanner.Buffer(make([]byte, 0, 64*1024), 2*1024*1024)
	jobs := make([]Job, 0)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var job Job
		if err := json.Unmarshal([]byte(line), &job); err != nil {
			return nil, err
		}
		if job.JobID == "" {
			return nil, errors.New("missing job_id")
		}
		if job.URL == "" {
			return nil, errors.New("missing url")
		}
		if job.DestRel == "" {
			return nil, errors.New("missing dest_rel")
		}
		jobs = append(jobs, job)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return jobs, nil
}

func main() {
	baseDir := flag.String("base-dir", ".", "base output directory")
	workers := flag.Int("workers", 8, "number of workers")
	timeout := flag.Int("timeout", 30, "request timeout seconds")
	retries := flag.Int("retries", 2, "retries per job")
	flag.Parse()

	jobs, err := readJobs(os.Stdin)
	if err != nil {
		_, _ = fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(2)
	}
	workerCount := *workers
	if workerCount < 1 {
		workerCount = 1
	}
	client := &http.Client{Timeout: time.Duration(max(*timeout, 1)) * time.Second}
	jobCh := make(chan Job)
	resultCh := make(chan Result)
	var wg sync.WaitGroup
	for i := 0; i < workerCount; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for job := range jobCh {
				resultCh <- processWithRetry(client, *baseDir, job, max(*retries, 0))
			}
		}()
	}
	go func() {
		wg.Wait()
		close(resultCh)
	}()
	go func() {
		for _, job := range jobs {
			jobCh <- job
		}
		close(jobCh)
	}()

	enc := json.NewEncoder(os.Stdout)
	for res := range resultCh {
		if err := enc.Encode(res); err != nil {
			_, _ = fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(3)
		}
	}
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
