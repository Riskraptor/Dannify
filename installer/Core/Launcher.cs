using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;

namespace Dannify.Setup.Core
{
    /// <summary>
    /// What &lt;root&gt;\Dannify.exe does every time Dannify is opened: put a
    /// waiting update in place if nothing is using the app, then start the
    /// app with whatever it was given. It is on screen for a few milliseconds.
    ///
    /// Updates are downloaded by the app, while it runs, into app-next\ with
    /// a .ready marker once every file checks out. Nothing touches app\ while
    /// the app is open, so nothing can be in use. The swap happens here, at
    /// the next start, as two renames.
    /// </summary>
    internal static class Launcher
    {
        public const string ReadyMarker = ".ready";

        public static bool HasPending(Env env) =>
            File.Exists(Path.Combine(env.NextDir, ReadyMarker)) && File.Exists(Path.Combine(env.NextDir, Env.ExeName));

        public static bool AppRunning(Env env) =>
            Apps.MutexExists(env.MutexName) || Apps.ProcessesUnder(env.AppDir).Count > 0;

        /// <summary>
        /// Swap in a waiting update. False (and nothing changed) if there is
        /// none, if the app is running, or if Windows will not let go of the
        /// folder within <paramref name="patienceMs"/>: the current version
        /// then simply runs, and the swap is tried again next time.
        /// </summary>
        public static bool TryApplyPending(Env env, int patienceMs)
        {
            if (!HasPending(env)) return false;
            if (AppRunning(env)) return false;

            using (var gate = new Mutex(false, @"Local\DannifySwap" + env.Instance))
            {
                bool owned;
                try
                {
                    owned = gate.WaitOne(15000);
                }
                catch (AbandonedMutexException)
                {
                    owned = true;
                }
                if (!owned) return false;
                try
                {
                    if (!HasPending(env) || AppRunning(env)) return false;
                    string parked = null;
                    if (Directory.Exists(env.AppDir))
                    {
                        parked = Files.Unique(Path.Combine(env.Root, "app-old"));
                        try
                        {
                            Files.MoveDir(env.AppDir, parked, patienceMs);
                        }
                        catch (Exception ex)
                        {
                            Log.Warn("update waits: the current version is still in use (" + ex.Message + ")");
                            return false;
                        }
                    }
                    try
                    {
                        Files.MoveDir(env.NextDir, env.AppDir, patienceMs);
                    }
                    catch (Exception ex)
                    {
                        Log.Error("could not put the update in place", ex);
                        if (parked != null)
                        {
                            try
                            {
                                Files.MoveDir(parked, env.AppDir, 30000);
                            }
                            catch (Exception back)
                            {
                                Log.Error("could not put the previous version back", back);
                            }
                        }
                        return false;
                    }
                    Log.Info("update applied: " + (Existing.FileVersion(env.AppExe) ?? "?"));
                    return true;
                }
                finally
                {
                    gate.ReleaseMutex();
                }
            }
        }

        /// <summary>
        /// app\ is missing (an interrupted swap, or something deleted it). A
        /// waiting update, or the version the last swap parked, can stand in.
        /// </summary>
        public static bool Recover(Env env)
        {
            if (File.Exists(env.AppExe)) return true;
            if (HasPending(env) && TryApplyPending(env, 5000) && File.Exists(env.AppExe)) return true;
            try
            {
                var parked = Directory.GetDirectories(env.Root, "app-old-*")
                    .Where(d => File.Exists(Path.Combine(d, Env.ExeName)))
                    .OrderByDescending(Directory.GetLastWriteTimeUtc)
                    .FirstOrDefault();
                if (parked != null)
                {
                    if (Directory.Exists(env.AppDir)) Files.MoveDir(env.AppDir, Files.Unique(Path.Combine(env.Root, "app-broken")), 5000);
                    Files.MoveDir(parked, env.AppDir, 5000);
                    Log.Warn("brought back " + Path.GetFileName(parked));
                    return File.Exists(env.AppExe);
                }
            }
            catch (Exception ex)
            {
                Log.Error("recovery failed", ex);
            }
            return false;
        }

        public static Process Start(Env env, IEnumerable<string> args)
        {
            var psi = new ProcessStartInfo(env.AppExe, JoinArguments(args))
            {
                UseShellExecute = false,
                WorkingDirectory = env.AppDir,
            };
            env.Prepare(psi);
            // Started by the user, so the app may take the foreground; this
            // hands that right on instead of leaving it flashing on the taskbar.
            Native.AllowSetForegroundWindow(Native.ASFW_ANY);
            return Process.Start(psi);
        }

        /// <summary>Quote arguments the way CommandLineToArgvW reads them back.</summary>
        public static string JoinArguments(IEnumerable<string> args)
        {
            var sb = new StringBuilder();
            foreach (var arg in args ?? Enumerable.Empty<string>())
            {
                if (sb.Length > 0) sb.Append(' ');
                if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
                {
                    sb.Append(arg);
                    continue;
                }
                sb.Append('"');
                int backslashes = 0;
                foreach (char c in arg)
                {
                    if (c == '\\')
                    {
                        backslashes++;
                        continue;
                    }
                    if (c == '"')
                    {
                        sb.Append('\\', backslashes * 2 + 1);
                        sb.Append('"');
                    }
                    else
                    {
                        sb.Append('\\', backslashes);
                        sb.Append(c);
                    }
                    backslashes = 0;
                }
                sb.Append('\\', backslashes * 2);
                sb.Append('"');
            }
            return sb.ToString();
        }

        /// <summary>
        /// The everyday start: no window of our own, nothing loaded that is not
        /// needed. False only when there is no app to start at all.
        /// </summary>
        public static bool RunQuick(Args args, Env env)
        {
            bool swapped = TryApplyPending(env, 3000);
            if (!File.Exists(env.AppExe) && !Recover(env)) return false;
            if (!swapped)
            {
                Start(env, args.PassThrough)?.Dispose();
                return true;
            }
            LaunchCare.StartWatched(env, args.PassThrough, true)?.Dispose();
            return true;
        }

        /// <summary>The visible top-level window of <paramref name="pid"/>, if it has one yet.</summary>
        public static IntPtr WindowOf(int pid, int minWidth = 240)
        {
            IntPtr found = IntPtr.Zero;
            Native.EnumWindows((h, _) =>
            {
                Native.GetWindowThreadProcessId(h, out int owner);
                if (owner != pid || !Native.IsWindowVisible(h)) return true;
                if (Native.GetWindowRect(h, out var r) && r.Right - r.Left >= minWidth)
                {
                    found = h;
                    return false;
                }
                return true;
            }, IntPtr.Zero);
            return found;
        }
    }
}
