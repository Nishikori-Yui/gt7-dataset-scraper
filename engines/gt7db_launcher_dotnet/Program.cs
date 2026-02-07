using System.Diagnostics;
using System.Text.Json;

namespace Gt7db.Launcher;

internal static class Program
{
    private static readonly string[] PythonCandidates = ["python3", "python"];

    private sealed record RuntimeLayout(
        bool IsPackaged,
        string RepoRoot,
        string WorkerRoot,
        string NativeDir,
        string PackageRoot,
        string ManifestPath);

    private sealed record Invocation(string WorkingDirectory, List<string> Arguments);

    public static int Main(string[] args)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help")
        {
            PrintUsage();
            return 0;
        }

        var command = args[0];
        var passthrough = args.Skip(1).ToList();

        var layout = ResolveRuntimeLayout();
        if (layout is null)
        {
            Console.Error.WriteLine("error: failed to locate runtime root (missing scripts/build_dbs.py or runtime/python/worker/scripts/build_dbs.py)");
            return 2;
        }

        if (command == "doctor")
        {
            return RunDoctor(layout, passthrough);
        }

        var python = ResolvePython(layout);
        if (python is null)
        {
            Console.Error.WriteLine(
                "error: no Python runtime found. Checked packaged runtime, local .venv, then system python3/python.");
            return 2;
        }

        var effective = BuildEffectiveArgs(command, passthrough, layout);
        var invocation = BuildInvocation(layout, command, effective);
        if (invocation is null)
        {
            Console.Error.WriteLine($"error: unsupported command '{command}'. Expected: scrape, build-dbs, query, doctor");
            return 2;
        }

        return RunPassthrough(python, invocation, layout);
    }

    private static List<string> BuildEffectiveArgs(string command, List<string> passthrough, RuntimeLayout layout)
    {
        var effective = new List<string>(passthrough);
        if (!layout.IsPackaged)
        {
            return effective;
        }

        if (command == "scrape")
        {
            EnsureArg(effective, "--engine", "hybrid");
            EnsureArg(effective, "--catalog-engine", "go");
            EnsureArg(effective, "--spec-engine", "rust");
            EnsureArg(effective, "--backend-fallback", "off");
            EnsureArg(effective, "--engines-dir", layout.NativeDir);
            return effective;
        }

        if (command == "build-dbs")
        {
            EnsureArg(effective, "--engine", "hybrid");
            EnsureArg(effective, "--catalog-engine", "go");
            EnsureArg(effective, "--spec-engine", "rust");
            EnsureArg(effective, "--merge-engine", "go");
            EnsureArg(effective, "--hero-check-engine", "rust");
            EnsureArg(effective, "--backend-fallback", "off");
            EnsureArg(effective, "--engines-dir", layout.NativeDir);
            EnsureArg(effective, "--merge-go-bin", ResolveBinary(layout.NativeDir, "gt7-db-merge-go"));
            EnsureArg(effective, "--hero-check-rust-bin", ResolveBinary(layout.NativeDir, "gt7-hero-check"));
            return effective;
        }

        if (command == "query")
        {
            var prefixed = new List<string>();
            AddArgIfMissing(prefixed, passthrough, "--query-engine", "go");
            AddArgIfMissing(prefixed, passthrough, "--query-fallback", "off");
            AddArgIfMissing(prefixed, passthrough, "--query-go-bin", ResolveBinary(layout.NativeDir, "gt7-query-go"));
            prefixed.AddRange(passthrough);
            return prefixed;
        }
        return effective;
    }

    private static Invocation? BuildInvocation(RuntimeLayout layout, string command, List<string> effectiveArgs)
    {
        var args = new List<string>();
        if (command == "scrape")
        {
            args.Add("-m");
            args.Add("gt7_scraper");
            args.AddRange(effectiveArgs);
            return new Invocation(Environment.CurrentDirectory, args);
        }

        if (command == "build-dbs")
        {
            var scriptPath = Path.Combine(layout.WorkerRoot, "scripts", "build_dbs.py");
            args.Add(scriptPath);
            args.AddRange(effectiveArgs);
            return new Invocation(Environment.CurrentDirectory, args);
        }

        if (command == "query")
        {
            args.Add("-m");
            args.Add("gt7_query");
            args.AddRange(effectiveArgs);
            return new Invocation(Environment.CurrentDirectory, args);
        }

        return null;
    }

    private static int RunPassthrough(string python, Invocation invocation, RuntimeLayout layout)
    {
        var psi = new ProcessStartInfo
        {
            FileName = python,
            WorkingDirectory = invocation.WorkingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
        };

        foreach (var arg in invocation.Arguments)
        {
            psi.ArgumentList.Add(arg);
        }

        var existingPythonPath = Environment.GetEnvironmentVariable("PYTHONPATH") ?? string.Empty;
        var workerPath = layout.WorkerRoot;
        psi.Environment["GT7DB_ROOT"] = workerPath;
        psi.Environment["GT7DB_NATIVE_DIR"] = layout.NativeDir;
        psi.Environment["PYTHONPATH"] = string.IsNullOrWhiteSpace(existingPythonPath)
            ? workerPath
            : workerPath + Path.PathSeparator + existingPythonPath;
        if (layout.IsPackaged)
        {
            var runtimeRoot = Path.Combine(layout.PackageRoot, "runtime");
            var nodeBin = Path.Combine(runtimeRoot, "node", "bin");
            var nodeRoot = Path.Combine(runtimeRoot, "node");
            var existingPath = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
            var prepend = new List<string>();
            if (Directory.Exists(nodeBin))
            {
                prepend.Add(nodeBin);
            }
            if (Directory.Exists(nodeRoot))
            {
                prepend.Add(nodeRoot);
            }
            if (prepend.Count > 0)
            {
                var joined = string.Join(Path.PathSeparator, prepend);
                psi.Environment["PATH"] = string.IsNullOrWhiteSpace(existingPath)
                    ? joined
                    : joined + Path.PathSeparator + existingPath;
            }

            var browsersPath = Path.Combine(runtimeRoot, "playwright", "browsers");
            if (Directory.Exists(browsersPath))
            {
                psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = browsersPath;
            }
        }

        using var proc = Process.Start(psi);
        if (proc is null)
        {
            Console.Error.WriteLine("error: failed to start child process");
            return 2;
        }
        proc.WaitForExit();
        return proc.ExitCode;
    }

    private static RuntimeLayout? ResolveRuntimeLayout()
    {
        var explicitRoot = Environment.GetEnvironmentVariable("GT7DB_ROOT");
        if (!string.IsNullOrWhiteSpace(explicitRoot))
        {
            var full = Path.GetFullPath(explicitRoot);
            if (File.Exists(Path.Combine(full, "scripts", "build_dbs.py")))
            {
                return new RuntimeLayout(
                    IsPackaged: false,
                    RepoRoot: full,
                    WorkerRoot: full,
                    NativeDir: Path.Combine(full, "local", "bin"),
                    PackageRoot: full,
                    ManifestPath: string.Empty);
            }
            if (File.Exists(Path.Combine(full, "runtime", "python", "worker", "scripts", "build_dbs.py")))
            {
                return BuildPackagedLayout(full);
            }
        }

        var baseDir = Path.GetFullPath(AppContext.BaseDirectory);
        foreach (var probe in ProbeDirs(baseDir, maxDepth: 8))
        {
            if (File.Exists(Path.Combine(probe, "scripts", "build_dbs.py")))
            {
                return new RuntimeLayout(
                    IsPackaged: false,
                    RepoRoot: probe,
                    WorkerRoot: probe,
                    NativeDir: Path.Combine(probe, "local", "bin"),
                    PackageRoot: probe,
                    ManifestPath: string.Empty);
            }
            if (File.Exists(Path.Combine(probe, "manifest.json")) &&
                File.Exists(Path.Combine(probe, "runtime", "python", "worker", "scripts", "build_dbs.py")))
            {
                return BuildPackagedLayout(probe);
            }
        }
        return null;
    }

    private static RuntimeLayout BuildPackagedLayout(string packageRoot)
    {
        var workerRoot = Path.Combine(packageRoot, "runtime", "python", "worker");
        var nativeDir = Path.Combine(packageRoot, "runtime", "native");
        return new RuntimeLayout(
            IsPackaged: true,
            RepoRoot: workerRoot,
            WorkerRoot: workerRoot,
            NativeDir: nativeDir,
            PackageRoot: packageRoot,
            ManifestPath: Path.Combine(packageRoot, "manifest.json"));
    }

    private static IEnumerable<string> ProbeDirs(string startDir, int maxDepth)
    {
        var dir = Path.GetFullPath(startDir);
        var depth = 0;
        while (!string.IsNullOrEmpty(dir) && depth <= maxDepth)
        {
            yield return dir;
            var parent = Directory.GetParent(dir);
            if (parent is null)
            {
                break;
            }
            dir = parent.FullName;
            depth += 1;
        }
    }

    private static string? ResolvePython(RuntimeLayout layout)
    {
        var explicitPython = Environment.GetEnvironmentVariable("GT7DB_PYTHON");
        if (!string.IsNullOrWhiteSpace(explicitPython) && ExecutableExists(explicitPython))
        {
            return explicitPython;
        }

        if (layout.IsPackaged)
        {
            var packagedCandidates = new[]
            {
                Path.Combine(layout.PackageRoot, "runtime", "python", "bin", "python3"),
                Path.Combine(layout.PackageRoot, "runtime", "python", "bin", "python"),
                Path.Combine(layout.PackageRoot, "runtime", "python", "python.exe"),
            };
            foreach (var candidate in packagedCandidates)
            {
                if (ExecutableExists(candidate))
                {
                    return candidate;
                }
            }
        }

        var venvUnix = Path.Combine(layout.RepoRoot, ".venv", "bin", "python");
        if (ExecutableExists(venvUnix))
        {
            return venvUnix;
        }

        var venvWindows = Path.Combine(layout.RepoRoot, ".venv", "Scripts", "python.exe");
        if (ExecutableExists(venvWindows))
        {
            return venvWindows;
        }

        foreach (var candidate in PythonCandidates)
        {
            if (ExecutableInPath(candidate))
            {
                return candidate;
            }
        }
        return null;
    }

    private static int RunDoctor(RuntimeLayout layout, List<string> args)
    {
        var json = args.Contains("--json");
        var defaults = new Dictionary<string, string[]>
        {
            ["scrape"] = ["--engine", "hybrid", "--catalog-engine", "go", "--spec-engine", "rust", "--backend-fallback", "off"],
            ["build-dbs"] = ["--engine", "hybrid", "--catalog-engine", "go", "--spec-engine", "rust", "--merge-engine", "go", "--hero-check-engine", "rust", "--backend-fallback", "off"],
            ["query"] = ["--query-engine", "go", "--query-fallback", "off"],
        };

        var payload = new Dictionary<string, object?>
        {
            ["packaged"] = layout.IsPackaged,
            ["worker_root"] = layout.WorkerRoot,
            ["native_dir"] = layout.NativeDir,
            ["manifest"] = layout.ManifestPath,
            ["defaults"] = defaults,
            ["python"] = ResolvePython(layout),
            ["native_bins"] = new Dictionary<string, string>
            {
                ["catalog"] = ResolveBinary(layout.NativeDir, "gt7-catalog-go"),
                ["downloader"] = ResolveBinary(layout.NativeDir, "gt7-downloader"),
                ["spec"] = ResolveBinary(layout.NativeDir, "gt7-spec-normalizer"),
                ["merge_go"] = ResolveBinary(layout.NativeDir, "gt7-db-merge-go"),
                ["hero_check"] = ResolveBinary(layout.NativeDir, "gt7-hero-check"),
                ["query_go"] = ResolveBinary(layout.NativeDir, "gt7-query-go"),
                ["playwright"] = ResolveBinary(layout.NativeDir, "gt7-playwright"),
            },
        };

        if (json)
        {
            Console.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }

        Console.WriteLine($"packaged: {layout.IsPackaged}");
        Console.WriteLine($"worker_root: {layout.WorkerRoot}");
        Console.WriteLine($"native_dir: {layout.NativeDir}");
        Console.WriteLine($"python: {payload["python"]}");
        Console.WriteLine("defaults:");
        foreach (var item in defaults)
        {
            Console.WriteLine($"  {item.Key}: {string.Join(" ", item.Value)}");
        }
        return 0;
    }

    private static void EnsureArg(List<string> args, string key, string value)
    {
        if (HasArg(args, key))
        {
            return;
        }
        args.Add(key);
        args.Add(value);
    }

    private static void AddArgIfMissing(List<string> target, List<string> source, string key, string value)
    {
        if (HasArg(source, key))
        {
            return;
        }
        target.Add(key);
        target.Add(value);
    }

    private static bool HasArg(List<string> args, string key)
    {
        for (var i = 0; i < args.Count; i++)
        {
            var current = args[i];
            if (current == key)
            {
                return true;
            }
            if (current.StartsWith(key + "=", StringComparison.Ordinal))
            {
                return true;
            }
        }
        return false;
    }

    private static string ResolveBinary(string nativeDir, string stem)
    {
        var direct = Path.Combine(nativeDir, stem);
        if (File.Exists(direct))
        {
            return direct;
        }
        var exe = direct + ".exe";
        if (File.Exists(exe))
        {
            return exe;
        }
        return direct;
    }

    private static bool ExecutableExists(string path)
    {
        return File.Exists(path);
    }

    private static bool ExecutableInPath(string fileName)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = fileName,
                ArgumentList = { "--version" },
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var proc = Process.Start(psi);
            if (proc is null)
            {
                return false;
            }
            proc.WaitForExit();
            return proc.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    private static void PrintUsage()
    {
        Console.WriteLine("gt7db <command> [args]");
        Console.WriteLine();
        Console.WriteLine("Commands:");
        Console.WriteLine("  scrape       Run scraper via Python core (python -m gt7_scraper)");
        Console.WriteLine("  build-dbs    Run dataset builder (python scripts/build_dbs.py)");
        Console.WriteLine("  query        Run query CLI (python -m gt7_query)");
        Console.WriteLine("  doctor       Show runtime layout and default backend profile");
    }
}
