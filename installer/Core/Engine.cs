using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Dannify.Setup.Core
{
    internal enum Step
    {
        Preparing,
        Copying,
        Checking,
        Closing,
        Finishing,
        Removing,
        Done,
    }

    internal sealed class InstallPlan
    {
        public string Root;
        public bool DesktopShortcut;
        public bool MayForceClose;
        public Func<bool> AskToForce;
    }

    /// <summary>
    /// Installing, updating and removing, with the window kept out of it.
    ///
    /// The order is the whole design. Everything that can fail for ordinary
    /// reasons (a damaged download, a full disk, a cancel) happens in a
    /// staging folder beside the app while the app may still be running.
    /// Only then is the running copy asked to close, and the finished folder
    /// is swapped in with two renames. Until that moment, failing leaves the
    /// PC exactly as it was.
    /// </summary>
    internal sealed class Engine
    {
        private readonly Env _env;
        public Action<Step, double> OnProgress;

        public Engine(Env env)
        {
            _env = env;
        }

        private void Report(Step step, double fraction) =>
            OnProgress?.Invoke(step, Math.Max(0.0, Math.Min(1.0, fraction)));

        public void Install(Payload payload, Existing existing, InstallPlan plan, CancellationToken ct)
        {
            string root = Path.GetFullPath(plan.Root).TrimEnd('\\');
            _env.Root = root;
            Log.Info("install " + payload.Version + " into " + root + " over " + existing.Kind + " " + existing.Version);

            Report(Step.Preparing, 0);
            CheckFolder(root);
            payload.VerifyChecksum(ct, f => Report(Step.Preparing, 0.05 * f));
            CheckSpace(root, payload.TotalSize);

            Directory.CreateDirectory(root);
            string stage = Files.Unique(Path.Combine(root, "app.partial"));
            string launcher = Files.Unique(Path.Combine(root, "Dannify.exe.new"));
            bool swapped = false;
            try
            {
                long total = Math.Max(1, payload.TotalSize);
                long unpacked = 0;
                payload.Extract(stage, ct, n =>
                    Report(Step.Copying, 0.05 + 0.75 * Interlocked.Add(ref unpacked, n) / total));
                long hashed = 0;
                payload.VerifyFiles(stage, ct, n =>
                    Report(Step.Checking, 0.80 + 0.10 * Interlocked.Add(ref hashed, n) / total));
                payload.WriteEngine(launcher);

                Report(Step.Closing, 0.90);
                Apps.CloseAll(_env, root, plan.MayForceClose, plan.AskToForce, ct);
                ct.ThrowIfCancellationRequested();

                // Nothing below this line is cancelled: stopping half way
                // through the swap is the one way to break an installation.
                Report(Step.Finishing, 0.92);
                PutAppInPlace(stage, root);
                swapped = true;
            }
            catch
            {
                if (!swapped)
                {
                    Files.TryDeleteDir(stage);
                    Files.TryDeleteFile(launcher);
                }
                throw;
            }

            // The new version is in place. What follows is bookkeeping: a
            // failure is logged, not reported, because the app works either way.
            Quietly("launcher", () => PutLauncherInPlace(launcher, root));
            if (existing.Kind == InstallKind.Legacy) Quietly("old files", () => RemoveLegacyFiles(root));
            Report(Step.Finishing, 0.95);
            Quietly("registration", () =>
            {
                long size = Files.DirSize(_env.AppDir) + new FileInfo(_env.LauncherExe).Length;
                Registration.Write(_env, payload.Version, size);
                Registration.RemoveLegacy(_env);
            });
            Report(Step.Finishing, 0.97);
            Quietly("shortcuts", () => MakeShortcuts(plan.DesktopShortcut, root));
            Quietly("tidy", () => Tidy(root));
            Log.Info("installed " + payload.Version);
            Report(Step.Done, 1);
        }

        private static void Quietly(string what, Action act)
        {
            try
            {
                act();
            }
            catch (Exception ex)
            {
                Log.Error("after install: " + what, ex);
            }
        }

        /// <summary>
        /// Folders an install must never go into. The uninstaller only removes
        /// what it put there, but a PC is no place to find out it was wrong.
        /// </summary>
        public static bool IsUnsuitable(string root, Env env)
        {
            try
            {
                string full = Path.GetFullPath(root).TrimEnd('\\');
                if (full.Length <= 3) return true; // a drive root
                var forbidden = new List<string>
                {
                    Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    Environment.GetFolderPath(Environment.SpecialFolder.MyMusic),
                    Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                    Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    Path.Combine(Env.LocalAppData, "Programs"),
                };
                foreach (var f in forbidden)
                {
                    if (string.IsNullOrEmpty(f)) continue;
                    if (string.Equals(full, f.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) return true;
                }
                string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
                if (!string.IsNullOrEmpty(windows) && Files.IsInside(full, windows)) return true;
                // Never inside the app's own data, where the uninstaller cleans up.
                if (!string.IsNullOrEmpty(env.DataDir) &&
                    (string.Equals(full, env.DataDir.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase) || Files.IsInside(full, env.DataDir)))
                    return true;
                return false;
            }
            catch
            {
                return true;
            }
        }

        private void CheckFolder(string root)
        {
            if (IsUnsuitable(root, _env)) throw new SetupException(Problem.BadFolder, root);
        }

        private static void CheckSpace(string root, long needed)
        {
            try
            {
                string drive = Path.GetPathRoot(root);
                if (string.IsNullOrEmpty(drive) || drive.StartsWith(@"\\", StringComparison.Ordinal)) return;
                var info = new DriveInfo(drive);
                long want = needed + 64L * 1024 * 1024;
                if (info.AvailableFreeSpace < want)
                    throw new SetupException(Problem.DiskFull, drive.TrimEnd('\\') + "|" + (want - info.AvailableFreeSpace));
            }
            catch (SetupException)
            {
                throw;
            }
            catch
            {
                // Could not tell: the copy itself will find out.
            }
        }

        private void PutAppInPlace(string stage, string root)
        {
            string app = Path.Combine(root, "app");
            string parked = null;
            if (Directory.Exists(app))
            {
                parked = Files.Unique(Path.Combine(root, "app-old"));
                Files.MoveDir(app, parked);
            }
            try
            {
                Files.MoveDir(stage, app);
            }
            catch
            {
                if (parked != null) Files.MoveDir(parked, app, 30000);
                throw;
            }
            // An update the old version had staged is older than this one.
            string next = Path.Combine(root, "app-next");
            if (Directory.Exists(next)) Files.TryDeleteDir(next);
        }

        private void PutLauncherInPlace(string fresh, string root)
        {
            string target = Path.Combine(root, Env.ExeName);
            string parked = null;
            if (File.Exists(target))
            {
                parked = Files.Unique(target + ".old");
                Files.MoveFile(target, parked);
            }
            try
            {
                Files.MoveFile(fresh, target);
            }
            catch
            {
                if (parked != null) Files.MoveFile(parked, target, 30000);
                throw;
            }
            if (parked != null) Files.TryDeleteFile(parked);
        }

        /// <summary>
        /// Dannify 3.x kept the app straight in this folder, with Inno Setup's
        /// uninstaller beside it. The new copy is in app\ now, so those go.
        /// </summary>
        private void RemoveLegacyFiles(string root)
        {
            foreach (var name in new[] { "runtime", "config" })
            {
                string dir = Path.Combine(root, name);
                if (!Directory.Exists(dir)) continue;
                if (Files.TryDeleteDir(dir, 8000)) continue;
                try
                {
                    Files.MoveDir(dir, Files.Unique(dir + ".old"));
                }
                catch (Exception ex)
                {
                    Log.Warn("left " + dir + " for later: " + ex.Message);
                }
            }
            foreach (var file in Directory.GetFiles(root))
            {
                string name = Path.GetFileName(file).ToLowerInvariant();
                if (name.StartsWith("unins", StringComparison.Ordinal) ||
                    name.EndsWith(".updating", StringComparison.Ordinal) ||
                    name.EndsWith(".old", StringComparison.Ordinal) ||
                    name.EndsWith(".new", StringComparison.Ordinal))
                    Files.TryDeleteFile(file);
            }
        }

        private void MakeShortcuts(bool desktop, string root)
        {
            Shortcuts.Create(_env.StartShortcut, _env.LauncherExe, root, "Dannify", Env.Aumid);

            // The old Setup made a Start menu folder with the app and an
            // uninstall entry in it. Settings > Apps is where removing an app
            // belongs now, so both go, and the folder with them if it is empty.
            string folder = _env.LegacyStartFolder;
            if (Directory.Exists(folder))
            {
                foreach (var lnk in Directory.GetFiles(folder, "*.lnk"))
                {
                    string target = Shortcuts.TargetOf(lnk);
                    if (target == null || Files.IsInside(target, root)) Files.TryDeleteFile(lnk);
                }
                if (!Directory.EnumerateFileSystemEntries(folder).Any())
                {
                    try
                    {
                        Directory.Delete(folder);
                    }
                    catch
                    {
                        // not empty after all
                    }
                }
            }

            if (desktop)
                Shortcuts.Create(_env.DesktopShortcut, _env.LauncherExe, root, "Dannify", Env.Aumid);
            else if (File.Exists(_env.DesktopShortcut) && Shortcuts.PointsInto(_env.DesktopShortcut, root))
                Files.TryDeleteFile(_env.DesktopShortcut);
        }

        /// <summary>Leftovers from earlier swaps and interrupted runs.</summary>
        public static void Tidy(string root)
        {
            if (!Directory.Exists(root)) return;
            foreach (var dir in Directory.GetDirectories(root))
            {
                string name = Path.GetFileName(dir).ToLowerInvariant();
                if (name.StartsWith("app-old-", StringComparison.Ordinal) ||
                    name.StartsWith("app.partial-", StringComparison.Ordinal) ||
                    name.StartsWith("runtime.old-", StringComparison.Ordinal) ||
                    name.StartsWith("config.old-", StringComparison.Ordinal))
                    Files.TryDeleteDir(dir, 1500);
            }
            foreach (var file in Directory.GetFiles(root))
            {
                string name = Path.GetFileName(file).ToLowerInvariant();
                if (name.StartsWith("dannify.exe.old-", StringComparison.Ordinal) ||
                    name.StartsWith("dannify.exe.new-", StringComparison.Ordinal))
                    Files.TryDeleteFile(file, 500);
            }
        }

        // ------------------------------------------------------------------
        // Removing
        // ------------------------------------------------------------------

        /// <summary>Runtime state, always removed: caches, the web view, and the sign-in.</summary>
        private static readonly string[] StateDirs = { "WebView2", "SignIn", "updates", "ytdlp-cache", "replaced" };
        private static readonly string[] StateFiles =
        {
            "account.json", "account.dat", "session.json", "direct_cache.json", "lyrics_cache.json",
            "clients.json", "instance.json", "port.json", "open.json", "window.json", "update-result.json",
        };

        /// <summary>Preferences, removed only when asked. The song store is never touched.</summary>
        private static readonly string[] SettingsFiles =
        {
            "settings.json", "lyric_offsets.json", "updates.json", "support.json",
        };

        public void Uninstall(bool removeSettings, bool mayForce, Func<bool> askToForce, CancellationToken ct)
        {
            string root = _env.Root;
            Log.Info("uninstall from " + root + (removeSettings ? " with settings" : ""));
            Report(Step.Closing, 0.05);
            Apps.CloseAll(_env, root, mayForce, askToForce, ct);

            Report(Step.Removing, 0.2);
            foreach (var lnk in new[] { _env.StartShortcut, _env.DesktopShortcut })
                if (File.Exists(lnk) && Shortcuts.PointsInto(lnk, root)) Files.TryDeleteFile(lnk);
            if (Directory.Exists(_env.LegacyStartFolder))
            {
                foreach (var lnk in Directory.GetFiles(_env.LegacyStartFolder, "*.lnk"))
                    if (Shortcuts.PointsInto(lnk, root)) Files.TryDeleteFile(lnk);
                try
                {
                    if (!Directory.EnumerateFileSystemEntries(_env.LegacyStartFolder).Any())
                        Directory.Delete(_env.LegacyStartFolder);
                }
                catch
                {
                    // leave it
                }
            }
            Registration.Remove(_env);
            Registration.RemoveLegacy(_env);

            Report(Step.Removing, 0.35);
            string self = Env.SelfPath;
            if (Directory.Exists(root))
            {
                foreach (var dir in Directory.GetDirectories(root))
                {
                    string name = Path.GetFileName(dir).ToLowerInvariant();
                    if (name == "app" || name == "app-next" || name == "runtime" || name == "config" ||
                        name.StartsWith("app-old-", StringComparison.Ordinal) ||
                        name.StartsWith("app.partial-", StringComparison.Ordinal) ||
                        name.StartsWith("app-next.", StringComparison.Ordinal) ||
                        name.StartsWith("runtime.old-", StringComparison.Ordinal) ||
                        name.StartsWith("config.old-", StringComparison.Ordinal))
                        Files.TryDeleteDir(dir, 8000);
                }
                Report(Step.Removing, 0.75);
                foreach (var file in Directory.GetFiles(root))
                {
                    if (string.Equals(Path.GetFullPath(file), self, StringComparison.OrdinalIgnoreCase)) continue;
                    string name = Path.GetFileName(file).ToLowerInvariant();
                    if (name == "dannify.exe" || name.StartsWith("dannify.exe.", StringComparison.Ordinal) ||
                        name == LaunchCare.SkipMarker ||
                        name.StartsWith("unins", StringComparison.Ordinal) || name.EndsWith(".updating", StringComparison.Ordinal))
                        Files.TryDeleteFile(file);
                }
            }

            Report(Step.Removing, 0.85);
            RemoveData(removeSettings);
            Report(Step.Done, 1);

            if (Files.IsInside(self, root)) ScheduleRemoval(self, root);
            else TryRemoveEmpty(root);
        }

        private void RemoveData(bool removeSettings)
        {
            string data = _env.DataDir;
            if (string.IsNullOrEmpty(data) || !Directory.Exists(data)) return;
            // The web view's helper processes outlive the app by a moment and
            // keep its folder open; its delete gets a longer wait.
            foreach (var name in StateDirs) Files.TryDeleteDir(Path.Combine(data, name), name == "WebView2" ? 10000 : 3000);
            foreach (var name in StateFiles) Files.TryDeleteFile(Path.Combine(data, name));
            if (removeSettings)
                foreach (var name in SettingsFiles) Files.TryDeleteFile(Path.Combine(data, name));
            foreach (var log in Directory.GetFiles(data, "*.log*"))
                if (!log.EndsWith("setup.log", StringComparison.OrdinalIgnoreCase)) Files.TryDeleteFile(log);
        }

        private static void TryRemoveEmpty(string root)
        {
            try
            {
                if (Directory.Exists(root) && !Directory.EnumerateFileSystemEntries(root).Any()) Directory.Delete(root);
            }
            catch
            {
                // something else lives there; it stays
            }
        }

        /// <summary>
        /// A running program cannot delete itself, so a hidden command prompt
        /// does it a moment after this one exits. Only the launcher and the
        /// folder, and the folder only if it is empty by then.
        /// </summary>
        private static void ScheduleRemoval(string self, string root)
        {
            try
            {
                string command = "/d /c ping -n 3 127.0.0.1 >nul & del /f /q \"" + self + "\" & rmdir \"" + root + "\"";
                var psi = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"), command)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden,
                    WorkingDirectory = Path.GetTempPath(),
                };
                Process.Start(psi)?.Dispose();
            }
            catch (Exception ex)
            {
                Log.Warn("could not schedule the last clean-up: " + ex.Message);
            }
        }

        // ------------------------------------------------------------------
        // A copy the old Setup installed for every user of the PC
        // ------------------------------------------------------------------

        /// <summary>
        /// Runs elevated (--remove-machine-copy). Removes a 3.x installation in
        /// Program Files, now that this user has their own copy, so the Start
        /// menu does not end up with two Dannifys in it.
        /// </summary>
        public static int RemoveMachineCopy(string dir)
        {
            try
            {
                string full = Path.GetFullPath(dir).TrimEnd('\\');
                string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
                string pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
                bool underProgramFiles = Files.IsInside(full, pf) || (!string.IsNullOrEmpty(pf86) && Files.IsInside(full, pf86));
                if (!underProgramFiles || !File.Exists(Path.Combine(full, Env.ExeName)) || !Directory.Exists(Path.Combine(full, "runtime")))
                {
                    Log.Warn("refused to remove " + full + ": does not look like a Dannify copy in Program Files");
                    return 2;
                }
                Apps.Kill(Apps.ProcessesUnder(full));
                Files.TryDeleteDir(full, 8000);

                using (var hklm = Microsoft.Win32.RegistryKey.OpenBaseKey(Microsoft.Win32.RegistryHive.LocalMachine, Microsoft.Win32.RegistryView.Registry64))
                {
                    hklm.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + Env.LegacyAppId, false);
                    string command = null;
                    using (var k = hklm.OpenSubKey(@"Software\Classes\" + Registration.ProgId + @"\shell\open\command"))
                        command = k?.GetValue("") as string;
                    if (command != null && command.IndexOf(full, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        hklm.DeleteSubKeyTree(@"Software\Classes\" + Registration.ProgId, false);
                        hklm.DeleteSubKeyTree(@"Software\Classes\Applications\" + Env.ExeName, false);
                        using (var k = hklm.OpenSubKey(@"Software\Classes\.dnf"))
                        {
                            if (k != null && string.Equals(k.GetValue("") as string, Registration.ProgId, StringComparison.OrdinalIgnoreCase))
                            {
                                k.Close();
                                hklm.DeleteSubKeyTree(@"Software\Classes\.dnf", false);
                            }
                        }
                    }
                }

                string common = Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms);
                string commonFolder = Path.Combine(common, "Dannify");
                if (Directory.Exists(commonFolder))
                {
                    foreach (var lnk in Directory.GetFiles(commonFolder, "*.lnk"))
                        if (Shortcuts.PointsInto(lnk, full)) Files.TryDeleteFile(lnk);
                    TryRemoveEmpty(commonFolder);
                }
                string publicDesktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory), "Dannify.lnk");
                if (File.Exists(publicDesktop) && Shortcuts.PointsInto(publicDesktop, full)) Files.TryDeleteFile(publicDesktop);
                Native.SHChangeNotify(Native.SHCNE_ASSOCCHANGED, 0, IntPtr.Zero, IntPtr.Zero);
                Log.Info("removed the copy in " + full);
                return 0;
            }
            catch (Exception ex)
            {
                Log.Error("removing the copy for all users", ex);
                return 1;
            }
        }
    }
}
