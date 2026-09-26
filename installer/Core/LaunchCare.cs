using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// Starting the app right after an update, and not leaving until it is
    /// clearly up.
    ///
    /// Two things can go wrong in that moment. The old copy's web view
    /// outlives it by a second or two and keeps its folder open; a new copy
    /// that starts inside that window cannot open it and exits at once. That
    /// is fixed by trying again. The other is a new version that cannot
    /// start at all. Then the version from before the update is put back and
    /// started instead, and the bad one is remembered so it is not fetched
    /// again.
    /// </summary>
    internal static class LaunchCare
    {
        public const string SkipMarker = ".skip-version";

        private enum Outcome
        {
            Up,
            HandedOff,
            Failed,
        }

        public static Process StartWatched(Env env, IEnumerable<string> args, bool afterUpdate)
        {
            var passThrough = (args ?? Enumerable.Empty<string>()).ToList();
            if (!File.Exists(env.AppExe) && !Launcher.Recover(env)) return null;

            Process app = null;
            Outcome outcome = Outcome.Failed;
            int attempts = afterUpdate ? 3 : 4;
            for (int attempt = 0; attempt < attempts; attempt++)
            {
                app = TryStart(env, passThrough);
                outcome = Watch(app, afterUpdate ? 15000 : 8000, out int code);
                if (outcome != Outcome.Failed) break;
                Log.Warn("start attempt " + (attempt + 1) + " ended with " + code);
                Thread.Sleep(attempt == 0 ? 2000 : 3000);
            }

            if (outcome == Outcome.Failed && afterUpdate && RollBack(env))
            {
                for (int attempt = 0; attempt < 3; attempt++)
                {
                    app = TryStart(env, passThrough);
                    outcome = Watch(app, 15000, out _);
                    if (outcome != Outcome.Failed) break;
                    Thread.Sleep(2500);
                }
            }

            if (afterUpdate && outcome != Outcome.Failed)
            {
                try
                {
                    string version = Existing.FileVersion(env.AppExe);
                    if (version != null) Registration.Refresh(env, version, Files.DirSize(env.AppDir));
                }
                catch (Exception ex)
                {
                    Log.Warn("could not refresh the version in Settings: " + ex.Message);
                }
                KeepOnlyPrevious(env.Root);
            }
            return app;
        }

        /// <summary>A program Windows will not even start counts as one that failed.</summary>
        private static Process TryStart(Env env, List<string> args)
        {
            try
            {
                return Launcher.Start(env, args);
            }
            catch (Exception ex)
            {
                Log.Warn("could not start the app: " + ex.Message);
                return null;
            }
        }

        private static Outcome Watch(Process app, int timeoutMs, out int exitCode)
        {
            exitCode = 0;
            if (app == null) return Outcome.Failed;
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < timeoutMs)
            {
                if (app.WaitForExit(150))
                {
                    exitCode = app.ExitCode;
                    // 0 is the single-instance path: another copy took the request.
                    return exitCode == 0 ? Outcome.HandedOff : Outcome.Failed;
                }
                if (Launcher.WindowOf(app.Id) != IntPtr.Zero) return Outcome.Up;
            }
            return Outcome.Up; // still running: slow to show, but alive
        }

        /// <summary>Put the version from before the update back in place.</summary>
        private static bool RollBack(Env env)
        {
            try
            {
                var parked = Directory.GetDirectories(env.Root, "app-old-*")
                    .Where(d => File.Exists(Path.Combine(d, Env.ExeName)))
                    .OrderByDescending(Directory.GetLastWriteTimeUtc)
                    .FirstOrDefault();
                if (parked == null) return false;
                // The release's own version, from the marker the update came
                // with: the program's file version is only what it says.
                string bad = ReadyVersion(env.AppDir) ?? Existing.FileVersion(env.AppExe);
                if (Launcher.AppRunning(env)) Apps.Kill(Apps.ProcessesUnder(env.AppDir));
                Files.MoveDir(env.AppDir, Files.Unique(Path.Combine(env.Root, "app-broken")), 10000);
                Files.MoveDir(parked, env.AppDir, 10000);
                if (!string.IsNullOrEmpty(bad)) File.WriteAllText(Path.Combine(env.Root, SkipMarker), bad);
                Log.Error("version " + bad + " could not start; went back to " + Existing.FileVersion(env.AppExe));
                return true;
            }
            catch (Exception ex)
            {
                Log.Error("could not go back to the previous version", ex);
                return false;
            }
        }

        private static string ReadyVersion(string appDir)
        {
            try
            {
                string marker = Path.Combine(appDir, Launcher.ReadyMarker);
                if (!File.Exists(marker)) return null;
                string version = Json.Str(Json.ParseObject(File.ReadAllText(marker)), "version");
                return string.IsNullOrWhiteSpace(version) ? null : version.Trim();
            }
            catch
            {
                return null;
            }
        }

        /// <summary>
        /// Keep the version before this one (for going back), and nothing
        /// older. Updates hard-link unchanged files, so the kept copy costs
        /// only the files that actually changed.
        /// </summary>
        public static void KeepOnlyPrevious(string root)
        {
            try
            {
                var parked = Directory.GetDirectories(root, "app-old-*")
                    .OrderByDescending(Directory.GetLastWriteTimeUtc)
                    .ToList();
                foreach (var dir in parked.Skip(1)) Files.TryDeleteDir(dir, 1500);
                foreach (var dir in Directory.GetDirectories(root, "app-broken-*")) Files.TryDeleteDir(dir, 1500);
                foreach (var dir in Directory.GetDirectories(root, "app.partial-*")) Files.TryDeleteDir(dir, 1500);
            }
            catch (Exception ex)
            {
                Log.Warn("tidy: " + ex.Message);
            }
        }
    }
}
