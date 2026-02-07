import { chromium } from "playwright";
import process from "node:process";
import readline from "node:readline";
function parseArgs(argv) {
    const out = {
        mode: "detail",
        locale: "gb",
        timeoutMs: 30000,
        workers: 1,
        carId: null,
    };
    for (let idx = 0; idx < argv.length; idx++) {
        const value = argv[idx];
        if (value === "--mode" && argv[idx + 1]) {
            const mode = argv[idx + 1];
            if (mode === "detail" || mode === "list-thumbs") {
                out.mode = mode;
            }
            idx += 1;
            continue;
        }
        if (value === "--locale" && argv[idx + 1]) {
            out.locale = argv[idx + 1];
            idx += 1;
            continue;
        }
        if (value === "--timeout-ms" && argv[idx + 1]) {
            out.timeoutMs = Math.max(1000, Number.parseInt(argv[idx + 1], 10) || 30000);
            idx += 1;
            continue;
        }
        if (value === "--workers" && argv[idx + 1]) {
            out.workers = Math.max(1, Number.parseInt(argv[idx + 1], 10) || 1);
            idx += 1;
            continue;
        }
        if (value === "--car-id" && argv[idx + 1]) {
            out.carId = argv[idx + 1];
            idx += 1;
            continue;
        }
    }
    return out;
}
async function getThumbMapFromPage(page, locale, timeoutMs) {
    const url = `https://www.gran-turismo.com/${locale}/gt7/carlist/`;
    page.setDefaultNavigationTimeout(timeoutMs);
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    try {
        await page.waitForLoadState("networkidle", { timeout: Math.min(timeoutMs, 10000) });
    }
    catch { }
    try {
        await page.waitForSelector("a[href*='/gt7/carlist/id/']", { timeout: Math.min(timeoutMs, 15000) });
    }
    catch { }
    try {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(800);
    }
    catch { }
    const rawMap = await page.evaluate(() => {
        const result = {};
        const addThumb = (carId, rawUrl, requireThumbPath) => {
            const value = (rawUrl || "").trim();
            if (!value)
                return;
            if (requireThumbPath && !value.includes("/car_thumbnails/"))
                return;
            const match = value.match(/(car\d+)/);
            const resolvedCarId = match?.[1] || carId;
            if (!resolvedCarId)
                return;
            const out = result[resolvedCarId] || [];
            if (!out.includes(value))
                out.push(value);
            result[resolvedCarId] = out;
        };
        const styleUrl = (styleText) => {
            const style = (styleText || "").trim();
            if (!style)
                return "";
            const match = style.match(/url\(["']?([^"')]+)["']?\)/i);
            return match?.[1] || "";
        };
        const parseSrcSet = (srcsetValue) => {
            const srcset = (srcsetValue || "").trim();
            if (!srcset)
                return [];
            return srcset
                .split(",")
                .map((part) => part.trim().split(/\s+/)[0] || "")
                .filter((item) => item.length > 0);
        };
        for (const img of Array.from(document.querySelectorAll("img"))) {
            const candidates = [
                img.getAttribute("src"),
                img.getAttribute("data-src"),
                img.getAttribute("data-original"),
                img.getAttribute("data-lazy-src"),
            ];
            for (const item of candidates)
                addThumb("", item, true);
            for (const item of parseSrcSet(img.getAttribute("srcset")))
                addThumb("", item, true);
            for (const item of parseSrcSet(img.getAttribute("data-srcset")))
                addThumb("", item, true);
        }
        for (const anchor of Array.from(document.querySelectorAll("a[href*='/gt7/carlist/id/']"))) {
            const href = anchor.getAttribute("href") || "";
            const hrefMatch = href.match(/\/id\/(car\d+)/);
            const carId = hrefMatch?.[1] || "";
            if (!carId)
                continue;
            const anchorImg = anchor.querySelector("img");
            const parentImg = anchor.parentElement?.querySelector("img") || null;
            const imgNodes = [anchorImg, parentImg];
            for (const node of imgNodes) {
                if (!node)
                    continue;
                const candidates = [
                    node.getAttribute("src"),
                    node.getAttribute("data-src"),
                    node.getAttribute("data-original"),
                    node.getAttribute("data-lazy-src"),
                ];
                for (const item of candidates)
                    addThumb(carId, item, false);
                for (const item of parseSrcSet(node.getAttribute("srcset")))
                    addThumb(carId, item, false);
                for (const item of parseSrcSet(node.getAttribute("data-srcset")))
                    addThumb(carId, item, false);
            }
            addThumb(carId, styleUrl(anchor.getAttribute("style")), false);
            addThumb(carId, styleUrl(anchor.parentElement?.getAttribute("style")), false);
        }
        return result;
    });
    const result = new Map();
    for (const [carId, thumbs] of Object.entries(rawMap)) {
        if (!Array.isArray(thumbs) || thumbs.length === 0)
            continue;
        result.set(carId, thumbs);
    }
    return result;
}
async function extractDetail(page, locale, carId, timeoutMs) {
    const url = `https://www.gran-turismo.com/${locale}/gt7/carlist/id/${carId}`;
    page.setDefaultNavigationTimeout(timeoutMs);
    try {
        await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    }
    catch {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    }
    const payload = await page.evaluate((cid) => {
        const textOf = (selector) => {
            const node = document.querySelector(selector);
            if (!node)
                return null;
            const text = (node.textContent || "").trim();
            return text.length > 0 ? text : null;
        };
        const specs = [];
        const rows = Array.from(document.querySelectorAll("table tr"));
        for (const row of rows) {
            const cells = row.querySelectorAll("th,td");
            if (cells.length < 2)
                continue;
            const key = (cells[0].textContent || "").trim();
            const value = (cells[1].textContent || "").trim();
            if (key && value)
                specs.push([key, value]);
        }
        if (specs.length === 0) {
            const dls = Array.from(document.querySelectorAll("dl"));
            for (const dl of dls) {
                const dts = Array.from(dl.querySelectorAll("dt"));
                const dds = Array.from(dl.querySelectorAll("dd"));
                for (let i = 0; i < Math.min(dts.length, dds.length); i++) {
                    const key = (dts[i].textContent || "").trim();
                    const value = (dds[i].textContent || "").trim();
                    if (key && value)
                        specs.push([key, value]);
                }
            }
        }
        const heroImages = Array.from(document.querySelectorAll("img"))
            .map((img) => (img.getAttribute("src") || "").trim())
            .filter((src) => src.length > 0 && src.includes(cid) && !src.includes("/car_thumbnails/"));
        const uniqueHeroImages = Array.from(new Set(heroImages));
        return {
            name: textOf("h1"),
            manufacturer_name: textOf("h2"),
            intro: textOf("h4"),
            detail: textOf("main p"),
            specs,
            hero_images: uniqueHeroImages,
        };
    }, carId);
    return payload;
}
async function readCarIdsFromStdin() {
    const ids = [];
    const rl = readline.createInterface({
        input: process.stdin,
        crlfDelay: Infinity,
    });
    for await (const line of rl) {
        const text = line.trim();
        if (!text)
            continue;
        try {
            const obj = JSON.parse(text);
            if (obj.car_id && obj.car_id.trim().length > 0)
                ids.push(obj.car_id.trim());
        }
        catch { }
    }
    return ids;
}
async function run() {
    const args = parseArgs(process.argv.slice(2));
    if (args.mode === "list-thumbs") {
        const browser = await chromium.launch();
        const page = await browser.newPage();
        const thumbMap = await getThumbMapFromPage(page, args.locale, args.timeoutMs);
        await browser.close();
        for (const [carId, thumbs] of thumbMap.entries()) {
            process.stdout.write(`${JSON.stringify({ car_id: carId, thumb_images: thumbs })}\n`);
        }
        return;
    }
    const carIds = args.carId ? [args.carId] : await readCarIdsFromStdin();
    if (carIds.length === 0)
        return;
    const browser = await chromium.launch();
    const queue = [...carIds];
    const workers = Math.max(1, args.workers);
    const tasks = [];
    for (let i = 0; i < workers; i++) {
        tasks.push((async () => {
            const page = await browser.newPage();
            while (queue.length > 0) {
                const carId = queue.shift();
                if (!carId)
                    break;
                try {
                    const detail = await extractDetail(page, args.locale, carId, args.timeoutMs);
                    process.stdout.write(`${JSON.stringify({
                        car_id: carId,
                        ok: true,
                        ...detail,
                    })}\n`);
                }
                catch (err) {
                    process.stdout.write(`${JSON.stringify({
                        car_id: carId,
                        ok: false,
                        error: err instanceof Error ? err.message : String(err),
                    })}\n`);
                }
            }
            await page.close();
        })());
    }
    await Promise.all(tasks);
    await browser.close();
}
run().catch((err) => {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`${message}\n`);
    process.exit(2);
});
