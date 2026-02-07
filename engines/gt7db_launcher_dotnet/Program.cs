using System.Diagnostics;

namespace Gt7db.Launcher;

internal static class Program
{
    private static readonly string[] PythonCandidates =
    [
        "python3",
        "python",
    ];

    public static int Main(string[] args)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help")
        {
            PrintUsage();
            return 0;
        }

        var command = args[0];
        var passthrough = args.Skip(1).ToArray();

        var repoRoot = ResolveRepoRoot();
        if (repoRoot is null)
        {
            Console.Error.WriteLine("error: failed to locate repository root (missing scripts/build_dbs.py)");
            return 2;
        }

        var python = ResolvePython(repoRoot);
        if (python is null)
        {
            Console.Error.WriteLine(
                "error: no Python runtime found. Checked packaged runtime, .venv, then system python3/python.");
            Console.Error.WriteLine("hint: run scripts/bootstrap_python_env.sh or scripts/bootstrap_hybrid_env.sh");
            return 2;
        }

        var invocation = BuildInvocation(repoRoot, command, passthrough);
        if (invocation is null)
        {
            Console.Error.WriteLine($"error: unsupported command '{command}'. Expected: scrape, build-dbs, query");
            return 2;
        }

        return RunPassthrough(python, invocation, repoRoot);
    }

    private static string? BuildInvocation(string repoRoot, string command, string[] passthrough)
    {
        static string Quote(string value) => value.Contains(' ') || value.Contains('"')
            ? $"\"{value.Replace("\"", "\\\"")}\""
            : value;

        var rest = string.Join(" ", passthrough.Select(Quote));
        return command switch
        {
            "scrape" => $"-m gt7_scraper {rest}".Trim(),
            "build-dbs" => $"{Quote(Path.Combine(repoRoot, "scripts", "build_dbs.py"))} {rest}".Trim(),
            "query" => $"-m gt7_query {rest}".Trim(),
            _ => null,
        };
    }

    private static int RunPassthrough(string python, string arguments, string workingDirectory)
    {
        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
        };

        using var proc = Process.Start(psi);
        if (proc is null)
        {
            Console.Error.WriteLine("error: failed to start child process");
            return 2;
        }
        proc.WaitForExit();
        return proc.ExitCode;
    }

    private static string? ResolveRepoRoot()
    {
        var current = Environment.GetEnvironmentVariable("GT7DB_ROOT");
        if (!string.IsNullOrWhiteSpace(current) &&
            File.Exists(Path.Combine(current, "scripts", "build_dbs.py")))
        {
            return Path.GetFullPath(current);
        }

        var baseDir = AppContext.BaseDirectory;
        foreach (var probe in ProbeDirs(baseDir))
        {
            if (File.Exists(Path.Combine(probe, "scripts", "build_dbs.py")))
            {
                return probe;
            }
        }
        return null;
    }

    private static IEnumerable<string> ProbeDirs(string startDir)
    {
        var dir = Path.GetFullPath(startDir);
        while (!string.IsNullOrEmpty(dir))
        {
            yield return dir;
            var parent = Directory.GetParent(dir);
            if (parent is null)
            {
                break;
            }
            dir = parent.FullName;
        }
    }

    private static string? ResolvePython(string repoRoot)
    {
        var explicitPython = Environment.GetEnvironmentVariable("GT7DB_PYTHON");
        if (!string.IsNullOrWhiteSpace(explicitPython) && ExecutableExists(explicitPython))
        {
            return explicitPython;
        }

        var packaged = Path.Combine(AppContext.BaseDirectory, "python", "bin", "python3");
        if (ExecutableExists(packaged))
        {
            return packaged;
        }

        var venv = Path.Combine(repoRoot, ".venv", "bin", "python");
        if (ExecutableExists(venv))
        {
            return venv;
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
                FileName = "/usr/bin/env",
                Arguments = fileName + " --version",
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
    }
}
